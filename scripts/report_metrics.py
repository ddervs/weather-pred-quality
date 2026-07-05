"""Headline verification tables from data/metrics/metrics.parquet.

Everything is re-aggregated from the stored sufficient statistics (error sums,
contingency counts) - derived columns are never averaged across segments.

Run: uv run scripts/report_metrics.py   (after scripts/run_metrics.py)
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import polars as pl

from wpq.config import STATIONS_FILE
from wpq.metrics import METRICS_FILE, STAT_COLS, with_derived

SEASONS = {12: "DJF", 1: "DJF", 2: "DJF", 3: "MAM", 4: "MAM", 5: "MAM",
           6: "JJA", 7: "JJA", 8: "JJA", 9: "SON", 10: "SON", 11: "SON"}


def rollup(df: pl.DataFrame, group: list[str]) -> pl.DataFrame:
    sums = df.group_by(group).agg([pl.col(c).sum() for c in STAT_COLS])
    return with_derived(sums).sort(group)


def main() -> None:
    m = pl.read_parquet(METRICS_FILE).filter(pl.col("lead_days") <= 5)
    stations = pl.DataFrame(json.loads(STATIONS_FILE.read_text())["stations"]).select(
        pl.col("id").alias("station_id"), "country", "area"
    )
    m = m.join(stations, on="station_id").with_columns(
        pl.col("month").dt.month().replace_strict(SEASONS).alias("season")
    )
    era5 = m.filter(pl.col("truth_source") == "era5")
    ukmo_era5 = era5.filter(pl.col("model") == "ukmo_seamless")

    with pl.Config(float_precision=2, tbl_rows=-1, tbl_hide_dataframe_shape=True,
                   tbl_hide_column_data_types=True, tbl_cell_numeric_alignment="RIGHT"):

        print("== Temperature MAE (deg C) by lead x nation | ukmo_seamless vs ERA5 ==")
        t = rollup(ukmo_era5.filter(pl.col("variable") == "temp_c"),
                   ["lead_days", "country"])
        print(t.pivot("country", index="lead_days", values="mae"), "\n")

        print("== Temperature MAE by lead x season | ukmo_seamless vs ERA5 ==")
        t = rollup(ukmo_era5.filter(pl.col("variable") == "temp_c"),
                   ["lead_days", "season"])
        print(t.pivot("season", index="lead_days", values="mae")
               .select("lead_days", "DJF", "MAM", "JJA", "SON"), "\n")

        print("== Rain occurrence (>=0.1 mm/h) by lead | ukmo_seamless vs ERA5 ==")
        r = rollup(ukmo_era5.filter(pl.col("variable") == "rain_occurred"),
                   ["lead_days"])
        print(r.select("lead_days", "n", "base_rate", "brier", "pod", "far",
                       "csi", "ets"), "\n")

        for var, label in (("temp_c", "Temperature MAE (deg C)"),
                           ("wind_ms", "Wind MAE (m/s)")):
            print(f"== {label} by lead x model vs ERA5 truth (mae == crps for "
                  "deterministic) ==")
            t = rollup(era5.filter(pl.col("variable") == var),
                       ["lead_days", "model"])
            piv = t.pivot("model", index="lead_days", values="mae")
            piv = piv.with_columns(
                (1 - pl.col("ukmo_seamless") / pl.col("persistence"))
                .alias("skill_vs_persist"),
                (1 - pl.col("ukmo_seamless") / pl.col("climatology_dayofyear"))
                .alias("skill_vs_clim"),
            )
            print(piv, "\n")

        print("== Live obs truth sources (collector started 2026-07-04; "
              "pairs so far) | ukmo_seamless ==")
        live = rollup(
            m.filter((pl.col("model") == "ukmo_seamless")
                     & (pl.col("truth_source") != "era5")),
            ["truth_source", "variable"],
        )
        print(live.select("truth_source", "variable", "n", "mae", "bias", "brier"))


if __name__ == "__main__":
    main()
