"""Calibration layer: how trustworthy are the forecasts, not just how accurate.

Reads data/norm/ (rebuild with `uv run scripts/run_metrics.py --normalize` if
missing) and writes three small Parquets under data/metrics/:

conformal.parquet - split-conformal prediction intervals for temperature.
    Mondrian groups: nation x lead_day (nation, not the finer region code, so every
    group keeps thousands of calibration points), plus a pooled 'UK' row per lead.
    Calibration set = 2024 valid times, test set = 2025-01-01 onwards - a clean
    temporal split, so coverage numbers are out-of-sample. Score = |error|, i.e.
    symmetric intervals: forecast +/- q_hat where q_hat is the ceil((n+1)(1-alpha))/n
    empirical quantile of calibration scores. Columns: country, lead_days, alpha,
    n_cal, q_hat (half-width, deg C), n_test, coverage (target 1-alpha).
    Exchangeability caveat: weather errors are serially correlated and the test
    period is a different climate sample than 2024 - coverage drift IS the finding.

brier_decomposition.parquet - Murphy decomposition of the rain-occurrence Brier
    score vs ERA5 by lead: brier = reliability - resolution + uncertainty.
    The forecast is still binary {0,1} (two bins), so this is scaffolding: the same
    code gives real reliability curves once MOGREPS member-fraction PoP lands
    (~4 weeks of ensemble collection, ~2026-08-01).

bootstrap_ci.parquet - 95 % CIs on the headline numbers: temperature MAE and rain
    ETS by lead (vs ERA5). Block bootstrap resampling station-days (hours within a
    station-day are strongly correlated; iid-hour resampling would be overconfident
    by roughly the sqrt of the block size). B = 1000, fixed seed.

Run: uv run scripts/run_calibration.py
"""

import json
import math

import numpy as np
import polars as pl

from wpq.config import DATA_DIR, STATIONS_FILE
from wpq.metrics import NORM_DIR, RAIN_THRESHOLD_MM

OUT_DIR = DATA_DIR / "metrics"
CAL_END = pl.datetime(2025, 1, 1)  # < : conformal calibration; >= : test
ALPHAS = (0.1, 0.2)
BOOTSTRAP_B = 1000
BOOTSTRAP_SEED = 20260705


def temp_pairs() -> pl.DataFrame:
    """prev_runs temperature forecasts joined to ERA5 truth, with nation."""
    fcst = (
        pl.read_parquet(NORM_DIR / "forecasts.parquet")
        .filter((pl.col("source") == "prev_runs") & (pl.col("variable") == "temp_c"))
        .with_columns((pl.col("lead_hours") // 24).cast(pl.Int32).alias("lead_days"))
        .select("station_id", "valid_time", "lead_days", pl.col("value").alias("f"))
    )
    obs = (
        pl.read_parquet(NORM_DIR / "observations.parquet")
        .filter((pl.col("source") == "era5") & (pl.col("variable") == "temp_c"))
        .select("station_id", "valid_time", pl.col("value").alias("o"))
    )
    nations = pl.DataFrame(json.loads(STATIONS_FILE.read_text())["stations"]).select(
        pl.col("id").alias("station_id"), "country"
    )
    return (
        fcst.join(obs, on=["station_id", "valid_time"])
        .join(nations, on="station_id")
        .with_columns((pl.col("f") - pl.col("o")).alias("err"))
    )


def rain_pairs() -> pl.DataFrame:
    """Binary rain forecasts vs ERA5 occurrence."""
    fcst = (
        pl.read_parquet(NORM_DIR / "forecasts.parquet")
        .filter((pl.col("source") == "prev_runs") & (pl.col("variable") == "precip_mm"))
        .with_columns(
            (pl.col("lead_hours") // 24).cast(pl.Int32).alias("lead_days"),
            (pl.col("value") >= RAIN_THRESHOLD_MM).cast(pl.Float64).alias("p"),
        )
        .select("station_id", "valid_time", "lead_days", "p")
    )
    obs = (
        pl.read_parquet(NORM_DIR / "observations.parquet")
        .filter((pl.col("source") == "era5") & (pl.col("variable") == "rain_occurred"))
        .select("station_id", "valid_time", pl.col("value").alias("o"))
    )
    return fcst.join(obs, on=["station_id", "valid_time"])


# ------------------------------------------------------------------- conformal

def conformal_quantile(scores: np.ndarray, alpha: float) -> float:
    """Finite-sample-valid split-conformal quantile of nonconformity scores."""
    n = len(scores)
    level = min(math.ceil((n + 1) * (1 - alpha)) / n, 1.0)
    return float(np.quantile(scores, level, method="higher"))


def build_conformal(pairs: pl.DataFrame) -> pl.DataFrame:
    cal = pairs.filter(pl.col("valid_time") < CAL_END)
    test = pairs.filter(pl.col("valid_time") >= CAL_END)
    rows = []
    groups = [(c,) for c in pairs["country"].unique().sort()] + [("UK",)]
    for (country,) in groups:
        expr = pl.lit(True) if country == "UK" else pl.col("country") == country
        for lead in sorted(pairs["lead_days"].unique()):
            c_scores = (cal.filter(expr & (pl.col("lead_days") == lead))["err"]
                        .abs().to_numpy())
            t_err = (test.filter(expr & (pl.col("lead_days") == lead))["err"]
                     .abs().to_numpy())
            if len(c_scores) < 100 or len(t_err) == 0:
                continue
            for alpha in ALPHAS:
                q = conformal_quantile(c_scores, alpha)
                rows.append({
                    "country": country, "lead_days": int(lead), "alpha": alpha,
                    "n_cal": len(c_scores), "q_hat": q,
                    "n_test": len(t_err),
                    "coverage": float((t_err <= q).mean()),
                })
    return pl.DataFrame(rows).sort("country", "lead_days", "alpha")


# ---------------------------------------------------- Brier decomposition (Murphy)

def build_brier_decomposition(pairs: pl.DataFrame) -> pl.DataFrame:
    rows = []
    for lead in sorted(pairs["lead_days"].unique()):
        sub = pairs.filter(pl.col("lead_days") == lead)
        n = sub.height
        obar = sub["o"].mean()
        bins = sub.group_by("p").agg(pl.len().alias("nk"), pl.col("o").mean().alias("ok"))
        rel = sum(nk * (pk - ok) ** 2 for pk, nk, ok in bins.iter_rows()) / n
        res = sum(nk * (ok - obar) ** 2 for _, nk, ok in bins.iter_rows()) / n
        unc = obar * (1 - obar)
        rows.append({
            "lead_days": int(lead), "n": n, "base_rate": obar,
            "brier": rel - res + unc, "reliability": rel,
            "resolution": res, "uncertainty": unc,
            "brier_skill": (res - rel) / unc,  # 1 - BS/BS_climatology
        })
    return pl.DataFrame(rows)


# ------------------------------------------------------------ block bootstrap CIs

def _bootstrap(block_stats: np.ndarray, statistic, rng) -> tuple[float, float]:
    """block_stats: (K, d) per-block sums; statistic: pooled sums (d,) -> float."""
    k = len(block_stats)
    reps = np.empty(BOOTSTRAP_B)
    for b in range(BOOTSTRAP_B):
        reps[b] = statistic(block_stats[rng.integers(0, k, k)].sum(axis=0))
    return float(np.quantile(reps, 0.025)), float(np.quantile(reps, 0.975))


def build_bootstrap_ci(temp: pl.DataFrame, rain: pl.DataFrame) -> pl.DataFrame:
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    day = pl.col("valid_time").dt.date().alias("day")
    rows = []
    for lead in sorted(temp["lead_days"].unique()):
        blocks = (
            temp.filter(pl.col("lead_days") == lead)
            .group_by("station_id", day)
            .agg(pl.len().alias("n"), pl.col("err").abs().sum().alias("sae"))
            .select("n", "sae").to_numpy()
        )
        mae = lambda s: s[1] / s[0]
        lo, hi = _bootstrap(blocks, mae, rng)
        rows.append({"metric": "temp_mae", "lead_days": int(lead),
                     "estimate": mae(blocks.sum(axis=0)),
                     "ci_lo": lo, "ci_hi": hi, "n_blocks": len(blocks)})
    for lead in sorted(rain["lead_days"].unique()):
        fb, ob = pl.col("p") >= 0.5, pl.col("o") >= 0.5
        blocks = (
            rain.filter(pl.col("lead_days") == lead)
            .group_by("station_id", day)
            .agg(h=(fb & ob).sum(), m=(~fb & ob).sum(),
                 fa=(fb & ~ob).sum(), cn=(~fb & ~ob).sum())
            .select("h", "m", "fa", "cn").to_numpy().astype(float)
        )
        def ets(s):
            h, m, fa, cn = s
            n = s.sum()
            hr = (h + m) * (h + fa) / n
            denom = h + m + fa - hr
            return (h - hr) / denom if abs(denom) > 1e-9 else float("nan")
        lo, hi = _bootstrap(blocks, ets, rng)
        rows.append({"metric": "rain_ets", "lead_days": int(lead),
                     "estimate": ets(blocks.sum(axis=0)),
                     "ci_lo": lo, "ci_hi": hi, "n_blocks": len(blocks)})
    return pl.DataFrame(rows)


# ------------------------------------------------------------------------- main

def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    temp = temp_pairs()
    rain = rain_pairs()

    conformal = build_conformal(temp)
    conformal.write_parquet(OUT_DIR / "conformal.parquet", compression="zstd")
    decomp = build_brier_decomposition(rain)
    decomp.write_parquet(OUT_DIR / "brier_decomposition.parquet", compression="zstd")
    ci = build_bootstrap_ci(temp, rain)
    ci.write_parquet(OUT_DIR / "bootstrap_ci.parquet", compression="zstd")

    with pl.Config(float_precision=3, tbl_rows=-1, tbl_hide_dataframe_shape=True,
                   tbl_hide_column_data_types=True):
        print("== Split-conformal 90% temp intervals (fit 2024, scored 2025-26; "
              "q_hat = half-width, deg C) ==")
        print(conformal.filter(pl.col("alpha") == 0.1)
              .pivot("country", index="lead_days", values="q_hat"), "\n")
        print("== Coverage of those intervals on 2025-26 (target 0.90) ==")
        print(conformal.filter(pl.col("alpha") == 0.1)
              .pivot("country", index="lead_days", values="coverage"), "\n")
        print("== Rain Brier decomposition vs ERA5 (binary forecast: 2 bins) ==")
        print(decomp, "\n")
        print("== 95% block-bootstrap CIs (station-day blocks, B=1000) ==")
        print(ci)


if __name__ == "__main__":
    main()
