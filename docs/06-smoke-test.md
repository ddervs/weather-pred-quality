# Backfill smoke test — pipeline verified (2026-07-04)

`scripts/backfill_ukmo.py` pulled UKMO (`ukmo_seamless`) forecasts at leads 0–5 days
(Open-Meteo Previous Runs API) plus ERA5 truth for all 33 registry stations,
2024-01-01 → 2026-06-30 (13.8 MB gzipped, `data/backfill/`). `scripts/smoke_metrics.py`
then scored ~2.9 M forecast–truth pairs:

| lead (days) | n (temp) | temp MAE °C | temp bias | wind MAE km/h | rain acc | POD | FAR |
|---|---|---|---|---|---|---|---|
| 0 | 722,304 | **0.70** | +0.06 | 3.36 | 84.7% | 49.4% | 23.5% |
| 1 | 534,204 | 0.84 | +0.04 | 3.74 | 83.0% | 42.6% | 31.7% |
| 2 | 459,690 | 1.03 | −0.10 | 3.57 | 80.8% | 54.1% | 40.9% |
| 3 | 433,059 | 1.15 | −0.15 | 4.27 | 77.7% | 50.5% | 46.5% |
| 4 | 390,687 | 1.36 | −0.10 | 4.98 | 75.7% | 46.2% | 52.5% |
| 5 | 425,997 | **1.63** | −0.10 | 5.95 | 74.0% | 38.5% | 58.4% |

Rain = precipitation ≥ 0.1 mm/h, truth = ERA5 reanalysis (not yet real gauges).

**Verdict: the pipeline is sound.** Temperature and wind error grow monotonically-ish
with lead, bias is small, rain false-alarm ratio doubles from day 0 to day 5 — all the
signatures a working verification chain must show. The station registry, previous-runs
retrieval, ERA5 alignment and hour-indexed join are wired correctly.

Notes for the real metrics engine (docs/PLAN.md next chunk):

- **`previous_day0` gotcha**: the Previous Runs API returns lead-0 under the *plain*
  variable name (`temperature_2m`), only leads ≥ 1 get the `_previous_dayN` suffix.
- The first version of the smoke script compared wind against precipitation via a
  positional-unpacking bug — caught because wind MAE was flat across leads and rain FAR
  was 0. Keep "does error grow with lead?" as a permanent regression check: it's an
  excellent tripwire for join/alignment/unit bugs.
- n varies by lead (some archive gaps per lead/model); per-lead sample composition
  differs slightly, which explains small non-monotonicities (wind at lead 2).
- ERA5 as truth flatters/blurs: real-gauge and station-obs truth (already being
  collected) will differ, especially for precipitation. These numbers are for pipeline
  validation, not publication.
- Rough headline, still: **UKMO ≈ 0.7 °C typical error same-day, ≈ 1.6 °C at five days**
  against ERA5 at UK stations — plausible vs published UKV verification.
