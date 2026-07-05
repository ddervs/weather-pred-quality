"""Metrics engine: data/norm/*.parquet -> data/metrics/metrics.parquet.

One row per (model, truth_source, variable, lead_days, station_id, month) holding
SUFFICIENT STATISTICS (n, error sums, contingency counts) plus derived metrics.
Reports must re-aggregate from the sums - never average the derived columns
(a mean of MAEs is not the pooled MAE). Region/country/season segmentation is
done at report time via stations.json + the month column.

Models:
    ukmo_seamless               deterministic UKMO (backfill prev_runs + live fetches)
    ukmo_global_ensemble_20km   MOGREPS-G control run only for now (member 0);
                                member-fraction PoP is a later chunk
    persistence                 obs from the same truth source 24*max(lead,1) h earlier
                                (lead 0 therefore duplicates lead 1 - can't persist 0 h)
    climatology_dayofyear       per station x variable x day-of-year x hour mean over
                                the ERA5 sample. CRUDE and in-sample (evaluated on the
                                same 2.5 y it was fitted on) - flagged, upgrade later.
                                Same value at every lead. For rain it is a frequency,
                                i.e. a probability: Brier is honest, the contingency
                                counts binarise it at 0.5.

Continuous stats: n, sum_err, sum_abs_err, sum_sq_err -> bias, mae, rmse.
CRPS for a deterministic forecast equals MAE - read mae as crps for ukmo_seamless.
Rain occurrence: forecast = precip_mm >= 0.1 as {0,1} (probabilistic upgrade later);
stats n, sum_brier, sum_fcst, sum_obs, hits, misses, false_alarms, correct_negatives
-> brier, base_rate, pod, far, csi, ets.

Run: uv run scripts/run_metrics.py
"""

from datetime import timedelta

import polars as pl

from wpq.config import DATA_DIR

NORM_DIR = DATA_DIR / "norm"
METRICS_FILE = DATA_DIR / "metrics" / "metrics.parquet"
RAIN_THRESHOLD_MM = 0.1
BASELINE_LEAD_DAYS = range(6)

GRAIN = ["model", "truth_source", "variable", "lead_days", "station_id", "month"]

STAT_COLS = ["n", "sum_err", "sum_abs_err", "sum_sq_err", "sum_brier",
             "sum_fcst", "sum_obs", "hits", "misses", "false_alarms",
             "correct_negatives"]


def load_norm() -> tuple[pl.DataFrame, pl.DataFrame]:
    fcst = (
        pl.read_parquet(NORM_DIR / "forecasts.parquet")
        # deterministic runs + ensemble control; members are a later chunk
        .filter(pl.col("member").is_null() | (pl.col("member") == 0))
        .with_columns((pl.col("lead_hours") // 24).cast(pl.Int32).alias("lead_days"))
        .select("model", "station_id", "valid_time", "lead_days", "variable", "value")
    )
    obs = (
        pl.read_parquet(NORM_DIR / "observations.parquet")
        .rename({"source": "truth_source", "value": "o"})
    )
    return fcst, obs


def _month() -> pl.Expr:
    return pl.col("valid_time").dt.truncate("1mo").dt.date().alias("month")


def agg_continuous(joined: pl.DataFrame) -> pl.DataFrame:
    err = pl.col("f") - pl.col("o")
    return (
        joined.with_columns(_month())
        .group_by(GRAIN)
        .agg(
            n=pl.len().cast(pl.Int64),
            sum_err=err.sum(),
            sum_abs_err=err.abs().sum(),
            sum_sq_err=(err ** 2).sum(),
        )
    )


def agg_binary(joined: pl.DataFrame) -> pl.DataFrame:
    """f is a probability in [0,1] (deterministic forecasts give {0,1}), o is {0,1}."""
    f, o = pl.col("f"), pl.col("o")
    fb, ob = f >= 0.5, o >= 0.5
    return (
        joined.with_columns(_month())
        .group_by(GRAIN)
        .agg(
            n=pl.len().cast(pl.Int64),
            sum_brier=((f - o) ** 2).sum(),
            sum_fcst=f.sum(),
            sum_obs=o.sum(),
            hits=(fb & ob).sum().cast(pl.Int64),
            misses=(~fb & ob).sum().cast(pl.Int64),
            false_alarms=(fb & ~ob).sum().cast(pl.Int64),
            correct_negatives=(~fb & ~ob).sum().cast(pl.Int64),
        )
    )


def model_stats(fcst: pl.DataFrame, obs: pl.DataFrame) -> list[pl.DataFrame]:
    """UKMO forecasts vs every obs source carrying the same variable."""
    continuous = fcst.join(
        obs.filter(pl.col("variable") != "rain_occurred"),
        on=["station_id", "valid_time", "variable"],
    ).rename({"value": "f"})

    rain_fcst = (
        fcst.filter(pl.col("variable") == "precip_mm")
        .with_columns(
            (pl.col("value") >= RAIN_THRESHOLD_MM).cast(pl.Float64).alias("f"),
            pl.lit("rain_occurred").alias("variable"),
        )
    )
    rain = rain_fcst.join(
        obs.filter(pl.col("variable") == "rain_occurred"),
        on=["station_id", "valid_time", "variable"],
    )
    return [agg_continuous(continuous), agg_binary(rain)]


def persistence_stats(obs: pl.DataFrame) -> list[pl.DataFrame]:
    """Forecast(valid, lead d) = same-source obs at valid - 24*max(d,1) h."""
    out = []
    for d in BASELINE_LEAD_DAYS:
        shifted = obs.select(
            "truth_source", "station_id", "variable",
            (pl.col("valid_time") + timedelta(hours=24 * max(d, 1))).alias("valid_time"),
            pl.col("o").alias("f"),
        )
        joined = shifted.join(
            obs, on=["truth_source", "station_id", "valid_time", "variable"]
        ).with_columns(
            pl.lit("persistence").alias("model"),
            pl.lit(d, dtype=pl.Int32).alias("lead_days"),
        )
        out.append(agg_continuous(joined.filter(pl.col("variable") != "rain_occurred")))
        out.append(agg_binary(joined.filter(pl.col("variable") == "rain_occurred")))
    return out


def climatology_stats(obs: pl.DataFrame) -> list[pl.DataFrame]:
    """Day-of-year x hour ERA5 mean as a lead-independent forecast for all truths."""
    doy_hour = [
        pl.col("valid_time").dt.ordinal_day().alias("doy"),
        pl.col("valid_time").dt.hour().alias("hour"),
    ]
    clim = (
        obs.filter(pl.col("truth_source") == "era5")
        .with_columns(doy_hour)
        .group_by("station_id", "variable", "doy", "hour")
        .agg(pl.col("o").mean().alias("f"))
    )
    joined = (
        obs.with_columns(doy_hour)
        .join(clim, on=["station_id", "variable", "doy", "hour"])
        .with_columns(
            pl.lit("climatology_dayofyear").alias("model"),
            pl.lit(0, dtype=pl.Int32).alias("lead_days"),
        )
    )
    lead0 = [
        agg_continuous(joined.filter(pl.col("variable") != "rain_occurred")),
        agg_binary(joined.filter(pl.col("variable") == "rain_occurred")),
    ]
    # identical at every lead: replicate the aggregated rows, not the joins
    return [
        df.with_columns(pl.lit(d, dtype=pl.Int32).alias("lead_days"))
        for df in lead0
        for d in BASELINE_LEAD_DAYS
    ]


def with_derived(stats: pl.DataFrame) -> pl.DataFrame:
    n = pl.col("n")
    h, m, fa = pl.col("hits"), pl.col("misses"), pl.col("false_alarms")
    hits_random = (h + m) * (h + fa) / n
    ets_denom = h + m + fa - hits_random
    safe = lambda num, den: pl.when(den > 0).then(num / den)
    return stats.with_columns(
        bias=pl.col("sum_err") / n,
        mae=pl.col("sum_abs_err") / n,
        rmse=(pl.col("sum_sq_err") / n).sqrt(),
        brier=pl.col("sum_brier") / n,
        base_rate=pl.when(pl.col("sum_obs").is_not_null()).then(pl.col("sum_obs") / n),
        pod=safe(h, h + m),
        far=safe(fa, h + fa),
        csi=safe(h, h + m + fa),
        ets=pl.when(ets_denom.abs() > 1e-9).then((h - hits_random) / ets_denom),
    )


def build() -> pl.DataFrame:
    fcst, obs = load_norm()
    parts = model_stats(fcst, obs) + persistence_stats(obs) + climatology_stats(obs)
    stats = pl.concat(parts, how="diagonal")
    stats = stats.select(GRAIN + [c for c in STAT_COLS if c in stats.columns])
    return with_derived(stats).sort(GRAIN)


def main() -> None:
    METRICS_FILE.parent.mkdir(parents=True, exist_ok=True)
    stats = build()
    stats.write_parquet(METRICS_FILE, compression="zstd")
    summary = (
        stats.group_by("model")
        .agg(pl.col("n").sum().alias("pairs"), pl.len().alias("rows"))
        .sort("model")
    )
    print(f"{METRICS_FILE.relative_to(DATA_DIR.parent)}: {stats.height:,} rows")
    for model, pairs, rows in summary.iter_rows():
        print(f"  {model:24} {pairs:>12,} fcst/obs pairs in {rows:>7,} segment rows")


if __name__ == "__main__":
    main()
