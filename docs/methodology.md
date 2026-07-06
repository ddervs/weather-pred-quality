# Methodology: how forecasts are scored

*Living doc. Last updated 2026-07-05. Describes what `wpq/metrics.py` and
`wpq/calibration.py` actually compute today. The research-phase survey of everything we
*could* compute is [research/03-metrics-and-calibration.md](research/03-metrics-and-calibration.md).*

## Ground rules

- **Everything is UTC** internally; timezone conversion happens only at display.
- **Score forecast runs, never "latest at fetch time"** — every row is keyed by
  `(init_time, valid_time)`, so a forecast is always judged at the lead it was made.
- **A score without a baseline is meaningless.** Every model score sits next to two
  pseudo-models computed identically: **persistence** ("tomorrow = today", i.e. the obs
  from `lead_days` ago) and **climatology** ("the average for this station,
  day-of-year and hour"). A forecast provider earns its keep only by beating both. The
  skill score is `SS = 1 − score/score_baseline` (1 = perfect, 0 = no better than
  baseline, negative = worse). Caveat: the current climatology is *in-sample* (a mean
  over the same 2.5 years it's scored on), which flatters the baseline; a 1991–2020
  normals upgrade is planned.
- **Sufficient statistics, aggregated late.** `metrics.parquet` stores sums and
  contingency counts per fine-grained cell; nation/season/UK numbers re-aggregate those
  sums. Averaging ready-made MAEs across cells with different `n` is wrong and banned.
- **Permanent regression check**: error must grow with lead time. It's an excellent
  tripwire for join/alignment/unit bugs (it caught a wind-vs-precipitation column swap
  during the smoke test).

## Continuous variables (temperature, wind): MAE, bias, RMSE

For each `(model, truth_source, variable, lead, station, month)` cell, with error
`e = forecast − observed`:

- **MAE** (mean |e|) — the headline: "typically off by 1.2 °C".
- **bias** (mean e) — systematic warm/cold or over/under tendency.
- **RMSE** (√mean e²) — punishes large misses; reported alongside, not headlined.

## Rain occurrence: contingency-table scores

The event is `rain_occurred` (≥ 0.1 mm in the hour; per-source definitions in
[data-layout.md](data-layout.md)). Heavier buckets exist as separate variables
`rain_ge_{0.5,1,2,4}` (mm/h, 2026-07-06) — derived from `precip_mm` on both the
forecast and observation side, so they are only scored against truth sources that
report amounts (ERA5 + the EA/SEPA/NRW gauges), not the code-based occurrence
sources (land_obs weather codes, METAR wx strings). Forecast is currently binarised
the same way as the event — a deterministic yes/no. Each pair lands in one of: **hit**, **miss** (it rained,
unforecast), **false alarm** (forecast, stayed dry), **correct negative**. From these:

- **POD** — hit rate: fraction of actual rain hours the forecast caught.
- **FAR** — false-alarm ratio: fraction of forecast rain hours that stayed dry.
- **CSI** — hits / (hits + misses + false alarms).
- **ETS** — the headline: CSI corrected for lucky hits by chance (standard at met
  centres; 0 = no skill beyond chance, 1 = perfect).
- **base_rate** — climatological rain frequency (~0.23 UK-wide), the anchor for skill.

## Probabilistic layer: Brier score and its Murphy decomposition

The **Brier score** is the mean squared error of a probability forecast of a binary
event (lower = better). Today's rain forecast is a hard 0/1, i.e. a probability claim of
absolute certainty — which is exactly what the decomposition punishes.

`wpq/calibration.py` computes the **Murphy decomposition**
`Brier = reliability − resolution + uncertainty`:

- **reliability** (lower = better): do claimed probabilities match observed frequencies?
- **resolution** (higher = better): do the forecast's categories actually separate rainy
  from dry situations?
- **uncertainty**: the base rate's own variance — a property of the weather, not the
  forecast.

Plus **Brier skill** vs always-quoting-the-base-rate. Current finding: negative from
day 2 (see [results/2026-07-05-calibration.md](results/2026-07-05-calibration.md)).
With only two bins (p ∈ {0,1}) "reliability" reduces to the miss/false-alarm rates of
each claim; real multi-bin reliability curves arrive with MOGREPS member-fraction PoP
(~2026-08), using this same code.

## Conformal prediction: intervals with guaranteed coverage

The differentiator. **Split conformal prediction** turns any point forecast into an
interval with a distribution-free coverage guarantee: measure |error| on a calibration
set, take the 90th-percentile quantile `q̂`, and "forecast ± q̂" then contains the truth
~90 % of the time on new data (if past and future errors are exchangeable).

As implemented (hand-rolled, ~no dependencies):

- Nonconformity score = |forecast − observed| for temperature.
- **Mondrian grouping** by `nation × lead_day`: a separate q̂ per cell, so coverage holds
  *within* each segment, not just on average (Scotland gets honestly wider intervals).
- Clean **temporal split**: calibrate on 2024, test on 2025-01 → 2026-06.
- Honesty caveat: exchangeability is technically violated (serial correlation, climate
  drift), so the observed coverage stability is an empirical result, not a theorem.
  Monitor the `coverage` column as the weekly CI job refreshes it.

## Uncertainty on the metrics themselves: block bootstrap

95 % CIs on headline metrics by resampling **station-days** (B = 1000, fixed seed), not
individual hours — errors within a station-day are strongly correlated, and iid-hour
resampling would understate the intervals. With ~700 k pairs per lead, CIs land at
±0.005–0.015, so every lead-to-lead difference reported so far is significant.

## Standing caveats (apply to all current results)

1. **Truth is ERA5**, a reanalysis model — it can share biases with UKMO and smooths
   local extremes. Redo vs live station obs once months accumulate.
2. **Cross-lead comparisons** inherit the Previous-Runs sample-composition caveat
   (different null patterns per lead).
3. **Climatology baseline is in-sample** and therefore flattered.

## Deliberate implementation choices

- Metrics are **hand-rolled in polars** rather than using the `scores` library (drags
  xarray/pandas for one-line closed forms) or MAPIE (same reasoning for conformal).
  The research survey of those libraries remains in
  [research/02-prior-art.md](research/02-prior-art.md) — revisit if needs outgrow
  closed forms.
- CRPS (the metric that would unify deterministic and ensemble comparison) is *planned*,
  not implemented — it becomes meaningful with ensemble PoP data.
