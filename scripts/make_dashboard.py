"""Build docs/dashboard.html - self-contained verification dashboard (v1, private).

Aggregates data/metrics/*.parquet into a compact JSON payload (per-scope lead
curves re-computed from sufficient statistics - never averaged MAEs), embeds it
in scripts/templates/dashboard.html along with the UK coastline, and writes one
offline-capable file. Scopes: UK, each nation, each station (map / chip / table
selection in the page).

Run: uv run scripts/make_dashboard.py [--screenshot [out.png]]
"""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import polars as pl

from wpq.config import DATA_DIR, STATIONS_FILE
from wpq.metrics import METRICS_FILE, STAT_COLS, with_derived

ROOT = Path(__file__).parent.parent
TEMPLATE = Path(__file__).parent / "templates" / "dashboard.html"
OUT_HTML = ROOT / "docs" / "dashboard.html"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
LEADS = list(range(6))
MODELS = ["ukmo_seamless", "persistence", "climatology_dayofyear"]
# bucket key (shown in the UI) -> metrics variable; "any" is the 0.1 mm/h default
RAIN_BUCKETS = [("any", "rain_occurred"), ("0.5", "rain_ge_0.5"),
                ("1", "rain_ge_1"), ("2", "rain_ge_2"), ("4", "rain_ge_4")]
# ERA5 backfill ends 2026-06-30; live station obs are truth from here on
CUTOVER = date(2026, 7, 1)
# a station-month cell can be truthed by several live sources (e.g. land_obs +
# metar temp at airports, gauge + land_obs rain) - keep only the best-ranked one
TRUTH_RANK = {"nrw_rain": 1, "sepa_rain": 2, "ea_rain": 3,
              "land_obs": 4, "metar": 5}

WRAPPER = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body style="margin:0">
{content}
</body>
</html>
"""


def rollup(df: pl.DataFrame, group: list[str]) -> pl.DataFrame:
    return with_derived(df.group_by(group).agg([pl.col(c).sum() for c in STAT_COLS]))


def curve(df: pl.DataFrame, model: str, variable: str, metric: str) -> list:
    """[metric at lead 0..5], None where absent, from pooled sufficient stats."""
    sub = df.filter((pl.col("model") == model) & (pl.col("variable") == variable))
    if sub.is_empty():
        return [None] * len(LEADS)
    vals = dict(rollup(sub, ["lead_days"]).select("lead_days", metric).iter_rows())
    return [round(vals[d], 3) if vals.get(d) is not None else None for d in LEADS]


def base_rate(df: pl.DataFrame, variable: str) -> float | None:
    sub = df.filter((pl.col("model") == "ukmo_seamless")
                    & (pl.col("variable") == variable))
    n, s = sub["n"].sum(), sub["sum_obs"].sum()
    return round(s / n, 4) if n else None


def scope_curves(df: pl.DataFrame) -> dict:
    return {
        "temp": {m: curve(df, m, "temp_c", "mae") for m in MODELS},
        "wind": {m: curve(df, m, "wind_ms", "mae") for m in MODELS},
        # climatology rain is a small probability -> binarised at 0.5 it never
        # forecasts rain, so its ETS is degenerate; show UKMO vs persistence
        "ets": {key: {m: curve(df, m, var, "ets")
                      for m in ("ukmo_seamless", "persistence")}
                for key, var in RAIN_BUCKETS},
        # how often each event actually happens at this scope (pooled base rate,
        # ERA5 truth) - context for near-zero skill on rare events
        "ebase": {key: base_rate(df, var) for key, var in RAIN_BUCKETS},
    }


def main() -> None:
    stations_meta = json.loads(STATIONS_FILE.read_text())["stations"]
    nations = pl.DataFrame(stations_meta).select(
        pl.col("id").alias("station_id"), "country"
    )
    all_m = pl.read_parquet(METRICS_FILE).filter(pl.col("lead_days") <= 5)
    era5 = all_m.filter(
        (pl.col("truth_source") == "era5") & (pl.col("month") < CUTOVER)
    )
    cell = ["model", "variable", "lead_days", "station_id", "month"]
    live = (
        all_m.filter((pl.col("truth_source") != "era5")
                     & (pl.col("month") >= CUTOVER))
        .with_columns(pl.col("truth_source").replace_strict(TRUTH_RANK)
                      .alias("rank"))
        .filter(pl.col("rank") == pl.col("rank").min().over(cell))
        .drop("rank")
    )
    m = pl.concat([era5, live]).join(nations, on="station_id")

    curves = {"UK": scope_curves(m)}
    for nation in sorted(m["country"].unique()):
        curves[f"nation:{nation}"] = scope_curves(m.filter(pl.col("country") == nation))
    for s in stations_meta:
        curves[f"station:{s['id']}"] = scope_curves(
            m.filter(pl.col("station_id") == s["id"])
        )

    per_station = rollup(
        m.filter((pl.col("model") == "ukmo_seamless")
                 & (pl.col("variable").is_in(["temp_c", "wind_ms", "rain_occurred"]))),
        ["station_id", "variable", "lead_days"],
    )
    stat_lookup = {
        (r["station_id"], r["variable"], r["lead_days"]): r
        for r in per_station.iter_rows(named=True)
    }

    def stat(sid, var, lead, metric):
        r = stat_lookup.get((sid, var, lead))
        return round(r[metric], 3) if r and r[metric] is not None else None

    stations = [
        {
            "id": s["id"], "name": s["seed_city"], "lat": s["lat"], "lon": s["lon"],
            "country": s["country"], "area": s["area"],
            "mae1": stat(s["id"], "temp_c", 1, "mae"),
            "mae5": stat(s["id"], "temp_c", 5, "mae"),
            "wind1": stat(s["id"], "wind_ms", 1, "mae"),
            "ets1": stat(s["id"], "rain_occurred", 1, "ets"),
            "n1": stat_lookup[(s["id"], "temp_c", 1)]["n"],
        }
        for s in stations_meta
    ]

    conformal = {}
    for r in pl.read_parquet(DATA_DIR / "metrics" / "conformal.parquet") \
               .filter(pl.col("alpha") == 0.1).iter_rows(named=True):
        c = conformal.setdefault(r["country"], {"q": [None] * 6, "cov": [None] * 6})
        c["q"][r["lead_days"]] = round(r["q_hat"], 2)
        c["cov"][r["lead_days"]] = round(r["coverage"], 3)

    brier = {k: [round(v, 3) for v in col]
             for k, col in pl.read_parquet(
                 DATA_DIR / "metrics" / "brier_decomposition.parquet")
             .sort("lead_days")
             .select(rel="reliability", res="resolution",
                     skill="brier_skill", base="base_rate")
             .to_dict(as_series=False).items()}

    ci = {}
    for r in pl.read_parquet(DATA_DIR / "metrics" / "bootstrap_ci.parquet") \
               .iter_rows(named=True):
        key = {"temp_mae": "temp", "rain_ets": "ets"}[r["metric"]]
        band = ci.setdefault(key, {"lo": [None] * 6, "hi": [None] * 6})
        band["lo"][r["lead_days"]] = round(r["ci_lo"], 3)
        band["hi"][r["lead_days"]] = round(r["ci_hi"], 3)

    # period end = latest collected day (land_obs is fetched on every collect run)
    last_day = max(p.name for p in (DATA_DIR / "raw" / "land_obs").iterdir()
                   if p.is_dir())
    payload = {
        "period": f"2024-01-01 → {last_day}", "truth": "ERA5 + station obs",
        "stations": stations, "curves": curves, "conformal": conformal,
        "brier": brier, "ci": ci,
    }
    coast = json.loads((ROOT / "data" / "geo" / "coast.json").read_text())
    content = (
        TEMPLATE.read_text()
        .replace("__COAST__", json.dumps(coast, separators=(",", ":")))
        .replace("__PAYLOAD__", json.dumps(payload, separators=(",", ":")))
    )
    OUT_HTML.write_text(WRAPPER.format(content=content))
    print(f"wrote {OUT_HTML} ({OUT_HTML.stat().st_size:,} B, "
          f"{len(curves)} scopes)")

    if "--screenshot" in sys.argv:
        idx = sys.argv.index("--screenshot")
        png = Path(sys.argv[idx + 1]) if len(sys.argv) > idx + 1 else \
            ROOT / "docs" / "dashboard.png"
        subprocess.run(
            [CHROME, "--headless", "--disable-gpu", f"--screenshot={png}",
             "--window-size=1180,2600", "--hide-scrollbars", f"file://{OUT_HTML}"],
            check=True, capture_output=True,
        )
        print(f"wrote {png} ({png.stat().st_size:,} B)")


if __name__ == "__main__":
    main()
