"""Weekly health report: data/raw + data/norm -> markdown for a GitHub issue.

Two red-amber-green tables (data sources, models) plus summary stats up top,
full per-station / per-lead detail in appendices. Posted Monday mornings by
.github/workflows/weekly-report.yml as an instantly-closed @-mention issue
(the scotbet pattern), so it arrives as a normal GitHub notification email.

RAG rules — all thresholds live in this file, tune here:

Sources (worst of the two signals wins):
  run completeness   RED no raw files this week | AMBER >2 missed runs | GREEN else
  station coverage   RED runs succeeded but zero usable rows | AMBER any expected
                     station silent, or stations below COVERAGE_OK hours | GREEN else
  Coverage denominator is each source's own first->latest valid hour in the
  window, so collection lag doesn't read as spottiness (staleness is alerted
  separately by scripts/check_source_alerts.py). METAR gets a looser bar:
  many airfields don't report overnight.

Models (per model x variable, pooled over leads 0-5, live truth only):
  metric = Brier for rain_occurred, MAE otherwise; baseline = previous
  BASELINE_WEEKS weeks of the same computation.
  GREY  baseline has < MIN_BASELINE_N pairs (early weeks) - absolute values only
  RED   no pairs at all, or metric > RED_RATIO x baseline
  AMBER metric > AMBER_RATIO x baseline, or pairs < half the baseline weekly rate
  GREEN else

Run: uv run python -m wpq.normalize && uv run scripts/make_weekly_report.py [--out report.md]
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wpq import metrics
from wpq.collect import raw_run_times
from wpq.config import STATIONS_FILE

WINDOW_DAYS = 7
BASELINE_WEEKS = 4
MIN_BASELINE_N = 500
RED_RATIO, AMBER_RATIO = 1.75, 1.25
MAX_MISSED_RUNS = 2
COVERAGE_OK = {"metar": 0.5}  # fraction of window hours; others use the default
COVERAGE_OK_DEFAULT = 0.8

LIVE_TRUTH = ["land_obs", "ea_rain", "sepa_rain", "nrw_rain", "metar"]
GREEN, AMBER, RED, GREY = "\U0001f7e2", "\U0001f7e0", "\U0001f534", "⚪"
RANK = {GREEN: 0, GREY: 1, AMBER: 2, RED: 3}
UNITS = {"temp_c": "degC", "wind_ms": "m/s", "gust_ms": "m/s", "precip_mm": "mm"}


def load_stations() -> list[dict]:
    return json.loads(STATIONS_FILE.read_text())["stations"]


def source_specs(stations: list[dict]) -> dict[str, dict]:
    """Expected cadence and station set per collector source."""
    def ids(key):
        return sorted(s["id"] for s in stations if s.get(key))
    every = sorted(s["id"] for s in stations)
    return {
        "ukmo_forecast": dict(per_day=4, kind="fcst", stations=every),
        "ukmo_ensemble": dict(per_day=2, kind="fcst", stations=every),
        "land_obs": dict(per_day=4, kind="obs", stations=every),
        "ea_rain": dict(per_day=4, kind="obs", stations=ids("ea_gauge")),
        "sepa_rain": dict(per_day=4, kind="obs", stations=ids("sepa_gauge")),
        "nrw_rain": dict(per_day=4, kind="obs", stations=ids("nrw_gauge")),
        "metar": dict(per_day=4, kind="obs", stations=ids("metar")),
    }


def worst(*statuses: str) -> str:
    return max(statuses, key=RANK.get)


def source_health(name: str, spec: dict, tables: dict[str, pl.DataFrame],
                  city: dict[str, str], start: datetime, now: datetime) -> dict:
    """One RAG row per source + its per-station coverage map (for appendix A)."""
    times = raw_run_times(name)
    row = dict(name=name, coverage={}, notes=[])
    if not times:
        return row | dict(status=RED, runs="0", stations=f"0/{len(spec['stations'])}",
                          notes=["no raw data has ever been collected"])
    # a source younger than the window is judged from its first file, not the window start
    eff_start = max(start, min(times))
    expected = max(1, round((now - eff_start).total_seconds() / 3600 * spec["per_day"] / 24))
    got = sum(t >= eff_start for t in times)
    if got == 0:
        run_status = RED
        row["notes"].append(f"no successful runs since {max(times):%Y-%m-%d %H:%M}Z")
    elif expected - got > MAX_MISSED_RUNS:
        run_status = AMBER
        row["notes"].append(f"{expected - got} missed runs")
    else:
        run_status = GREEN
    row["runs"] = f"{got}/{expected}"

    # coverage is filtered on the window start, not eff_start: gauge payloads
    # cover the 30 h BEFORE each fetch, so valid times precede the first file
    df = tables[spec["kind"]]
    time_col = "valid_time" if spec["kind"] == "obs" else "init_time"
    df = df.filter((pl.col("source") == name) & (pl.col(time_col) >= start))
    if df.is_empty():
        row["notes"].append("runs succeeded but produced no usable rows")
        return row | dict(status=worst(run_status, RED),
                          stations=f"0/{len(spec['stations'])}")
    # denominator = the source's own observed span (obs) or run count (fcst), so
    # collection lag - a run-completeness/staleness problem - doesn't read as spottiness.
    # Span starts at the MEDIAN station's first timestamp: one deep-history outlier
    # (EA's hourly gauges return 5 days per fetch) must not dilute everyone else.
    if spec["kind"] == "obs":
        span_start = df.group_by("station_id").agg(
            pl.col(time_col).min()).get_column(time_col).median()
        df = df.filter(pl.col(time_col) >= span_start)
        denom = max(1.0, (df[time_col].max() - span_start).total_seconds() / 3600 + 1)
    else:
        denom = df[time_col].n_unique()
    per = dict(df.group_by("station_id").agg(pl.col(time_col).n_unique()).iter_rows())
    row["coverage"] = {sid: per.get(sid, 0) / denom for sid in spec["stations"]}
    silent = [sid for sid, c in row["coverage"].items() if c == 0]
    ok = COVERAGE_OK.get(name, COVERAGE_OK_DEFAULT)
    spotty = [sid for sid, c in row["coverage"].items() if 0 < c < ok]
    cov_status = GREEN
    if silent:
        cov_status = AMBER
        names = ", ".join(city.get(s, s) for s in silent[:4])
        row["notes"].append(f"{len(silent)} station(s) silent: {names}")
    if spotty:
        cov_status = AMBER
        names = ", ".join(city.get(s, s) for s in spotty[:4])
        row["notes"].append(f"{len(spotty)} station(s) below {ok:.0%} coverage: {names}")
    row["stations"] = f"{len(spec['stations']) - len(silent)}/{len(spec['stations'])}"
    return row | dict(status=worst(run_status, cov_status))


def window_stats(fcst: pl.DataFrame, obs: pl.DataFrame,
                 t0: datetime, t1: datetime, keys: list[str]) -> pl.DataFrame:
    """Forecast-vs-live-obs sufficient stats for valid times in [t0, t1), pooled to keys."""
    f = fcst.filter((pl.col("valid_time") >= t0) & (pl.col("valid_time") < t1))
    o = obs.filter((pl.col("valid_time") >= t0) & (pl.col("valid_time") < t1)
                   & pl.col("truth_source").is_in(LIVE_TRUTH))
    parts = pl.concat(metrics.model_stats(f, o), how="diagonal")
    if parts.is_empty():
        return parts
    present = [c for c in metrics.STAT_COLS if c in parts.columns]
    return metrics.with_derived(
        parts.group_by(keys).agg([pl.col(c).sum() for c in present]))


def metric_of(variable: str) -> str:
    # rain_occurred and the rain_ge_* buckets are binary events (metrics.add_rain_events)
    return "brier" if variable.startswith("rain") else "mae"


def model_health(week: pl.DataFrame, base: pl.DataFrame) -> list[dict]:
    """One RAG row per model x variable: this week vs the trailing-weeks baseline."""
    rows = []
    week_d = {(r["model"], r["variable"]): r for r in week.iter_rows(named=True)}
    base_d = {(r["model"], r["variable"]): r for r in base.iter_rows(named=True)}
    for key in sorted(week_d | base_d):
        model, variable = key
        m = metric_of(variable)
        w, b = week_d.get(key), base_d.get(key)
        wn, bn = (w or {}).get("n", 0), (b or {}).get("n", 0)
        wv = w[m] if w else None
        bv = b[m] if b else None
        row = dict(model=model, variable=variable, metric=m,
                   week=wv, base=bv, week_n=wn, base_n=bn, notes=[])
        if bn < MIN_BASELINE_N:
            if wn == 0:
                row |= dict(status=RED, notes=["no forecast/obs pairs this week"])
            else:
                row |= dict(status=GREY, notes=["no baseline yet (needs ~4 weeks of live obs)"])
        elif wn == 0:
            row |= dict(status=RED, notes=["no forecast/obs pairs this week"])
        elif bv and bv > 1e-9 and wv / bv > RED_RATIO:
            row |= dict(status=RED, notes=[f"{m} {wv / bv:.2f}x baseline"])
        elif bv and bv > 1e-9 and wv / bv > AMBER_RATIO:
            row |= dict(status=AMBER, notes=[f"{m} {wv / bv:.2f}x baseline"])
        elif wn < 0.5 * bn / BASELINE_WEEKS:
            row |= dict(status=AMBER, notes=["pair count under half the baseline rate"])
        else:
            row |= dict(status=GREEN)
        rows.append(row)
    return rows


def fmt(v, variable: str) -> str:
    if v is None:
        return "-"
    if variable.startswith("rain"):  # binary events: unitless Brier scores
        return f"{v:.3f}"
    return f"{v:.2f} {UNITS[variable]}"


def build_report(now: datetime) -> str:
    start = now - timedelta(days=WINDOW_DAYS)
    stations = load_stations()
    specs = source_specs(stations)
    city = {s["id"]: s["seed_city"] for s in stations}

    fcst_norm = pl.read_parquet(metrics.NORM_DIR / "forecasts.parquet")
    obs_norm = pl.read_parquet(metrics.NORM_DIR / "observations.parquet")
    tables = {"fcst": fcst_norm, "obs": obs_norm}
    src_rows = [source_health(n, spec, tables, city, start, now)
                for n, spec in specs.items()]

    fcst, obs = metrics.load_norm()
    week = window_stats(fcst, obs, start, now, ["model", "variable"])
    base = window_stats(fcst, obs, start - timedelta(weeks=BASELINE_WEEKS), start,
                        ["model", "variable"])
    mdl_rows = model_health(week, base)
    by_lead = window_stats(fcst, obs, start, now, ["model", "variable", "lead_days"])

    n_green = sum(r["status"] == GREEN for r in src_rows)
    obs_week = obs_norm.filter((pl.col("valid_time") >= start)
                               & pl.col("source").is_in(LIVE_TRUTH))
    pairs_week = week["n"].sum() if not week.is_empty() else 0

    L = [f"# Weekly health report — {start:%Y-%m-%d} → {now:%Y-%m-%d}", ""]
    L += [f"**{n_green}/{len(src_rows)} sources green** · "
          f"{obs_week.height:,} live observation rows · "
          f"{pairs_week:,} forecast/obs pairs scored this week.", ""]

    L += ["## Data sources", "",
          "| | Source | Runs | Stations | Notes |", "|--|--|--|--|--|"]
    for r in src_rows:
        L.append(f"| {r['status']} | `{r['name']}` | {r['runs']} | {r['stations']} | "
                 f"{'; '.join(r['notes'])} |")
    L += ["", "Runs = successful collector runs / expected (6-hourly; ensembles 2/day). "
          "Stations = stations that delivered any data / expected. Sources younger than "
          "the window are judged from their first collection.", ""]

    L += ["## Models — last 7 days vs live observations", "",
          "| | Model | Variable | Metric | This week | Baseline (4w) | Pairs | Notes |",
          "|--|--|--|--|--|--|--|--|"]
    for r in mdl_rows:
        L.append(f"| {r['status']} | `{r['model']}` | {r['variable']} | {r['metric']} | "
                 f"{fmt(r['week'], r['variable'])} | {fmt(r['base'], r['variable'])} | "
                 f"{r['week_n']:,} | {'; '.join(r['notes'])} |")
    L += ["", "Pooled over leads 0–5 and all live truth sources "
          "(ERA5 backfill excluded — it is static). MAE for continuous variables, "
          "Brier for rain occurrence; lower is better.", ""]

    L += ["---", "", "## Appendix A — station coverage (fraction of hours with data)", "",
          "| Station | " + " | ".join(f"`{r['name']}`" for r in src_rows) + " |",
          "|--|" + "--|" * len(src_rows)]
    for sid in sorted(city, key=city.get):
        cells = []
        for r in src_rows:
            if sid not in r["coverage"]:
                cells.append("·")
            else:
                c = r["coverage"][sid]
                cells.append("✓" if c >= 0.95 else ("✗" if c == 0 else f"{c:.0%}"))
        L.append(f"| {city[sid]} | " + " | ".join(cells) + " |")
    L += ["", "✓ ≥95% of the source's observed span · ✗ silent · · not expected "
          "(no paired gauge/airport).", ""]

    L += ["## Appendix B — per-lead metrics (this week)", ""]
    if by_lead.is_empty():
        L.append("_No pairs this week._")
    else:
        leads = list(range(6))
        L += ["| Model | Variable | " + " | ".join(f"d{d}" for d in leads) + " | Pairs |",
              "|--|--|" + "--|" * (len(leads) + 1)]
        idx = {(r["model"], r["variable"], r["lead_days"]): r
               for r in by_lead.iter_rows(named=True)}
        for model, variable in sorted({(r["model"], r["variable"])
                                       for r in by_lead.iter_rows(named=True)}):
            m = metric_of(variable)
            vals = [idx.get((model, variable, d)) for d in leads]
            n = sum(v["n"] for v in vals if v)
            cells = [f"{v[m]:.2f}" if v and v[m] is not None else "-" for v in vals]
            L.append(f"| `{model}` | {variable} ({m}) | " + " | ".join(cells)
                     + f" | {n:,} |")
    L += ["", f"_Generated {now:%Y-%m-%d %H:%M}Z by weekly-report.yml; RAG thresholds "
          "live in scripts/make_weekly_report.py._"]
    return "\n".join(L) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="report.md")
    args = ap.parse_args()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    report = build_report(now)
    Path(args.out).write_text(report)
    print(f"wrote {args.out} ({len(report):,} chars)")


if __name__ == "__main__":
    main()
