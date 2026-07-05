# 07 — First real metrics (normalisation layer + metrics engine)

*2026-07-05. Produced by the new pipeline: `wpq/normalize.py` → `data/norm/*.parquet`,
`wpq/metrics.py` (via `scripts/run_metrics.py`) → `data/metrics/metrics.parquet`,
tables printed by `scripts/report_metrics.py`. Sample: 33 stations, 2024-01-01..2026-06-30
UKMO `ukmo_seamless` backfill vs ERA5 truth, plus 1 day of live collection.*

## Acceptance check — pipeline reproduces the smoke test

Temperature MAE vs ERA5 by lead: **0.70, 0.84, 1.03, 1.15, 1.36, 1.63 °C** for leads
0–5 d — identical to the dependency-free smoke test (docs/06). The Parquet path, unit
conversions and joins introduce no drift. "Error grows with lead" holds everywhere and
stays the permanent regression check.

## Headline: temperature MAE (°C) by lead × nation (truth = ERA5)

| lead (d) | England | N. Ireland | Scotland | Wales |
|---|---|---|---|---|
| 0 | 0.67 | 0.67 | 0.85 | 0.71 |
| 1 | 0.81 | 0.80 | 0.95 | 0.83 |
| 2 | 1.03 | 1.07 | 1.05 | 1.00 |
| 3 | 1.14 | 1.20 | 1.16 | 1.09 |
| 4 | 1.36 | 1.36 | 1.39 | 1.27 |
| 5 | 1.64 | 1.61 | 1.62 | 1.55 |

Scotland is hardest at short leads (terrain), but nations converge by day 3 — at long
lead the error is synoptic, not local. Seasonally, JJA is easiest at long lead
(1.50 °C day 5) and DJF/MAM hardest (~1.7 °C): winter regimes and spring convection.

## Rain occurrence (≥0.1 mm/h, forecast binarised) vs ERA5

| lead (d) | base rate | Brier | POD | FAR | CSI | ETS |
|---|---|---|---|---|---|---|
| 0 | 0.23 | 0.15 | 0.49 | 0.24 | 0.43 | 0.34 |
| 1 | 0.22 | 0.17 | 0.43 | 0.32 | 0.36 | 0.27 |
| 2 | 0.23 | 0.19 | 0.54 | 0.41 | 0.39 | 0.28 |
| 3 | 0.24 | 0.22 | 0.50 | 0.47 | 0.35 | 0.23 |
| 4 | 0.23 | 0.24 | 0.46 | 0.52 | 0.31 | 0.18 |
| 5 | 0.23 | 0.26 | 0.39 | 0.58 | 0.25 | 0.13 |

ETS decays 0.34 → 0.13; by day 5 FAR is 58 %. The non-monotone POD at leads 1–2 is a
sample-composition artefact: the previous-runs API returns nulls for a varying subset
of hours at leads ≥1 (coverage 55–75 %), so different leads see different weather mixes.
Comparisons **across** leads are indicative; comparisons **at** a lead are solid.

## Skill vs baselines (temperature MAE, truth = ERA5)

| lead (d) | climatology | persistence | ukmo | skill vs persist | skill vs clim |
|---|---|---|---|---|---|
| 0 | 1.75 | 1.98 | 0.70 | 0.65 | 0.60 |
| 1 | 1.75 | 1.98 | 0.84 | 0.58 | 0.52 |
| 2 | 1.75 | 2.49 | 1.03 | 0.59 | 0.41 |
| 3 | 1.75 | 2.74 | 1.15 | 0.58 | 0.35 |
| 4 | 1.75 | 2.89 | 1.36 | 0.53 | 0.22 |
| 5 | 1.75 | 3.03 | 1.63 | 0.46 | 0.07 |

- Temperature: UKMO beats both baselines at every lead, but the margin over
  climatology shrinks to **7 % by day 5** — and this climatology is crude
  (station × day-of-year × hour mean over the same 2.5 y it's scored on, i.e.
  in-sample and flattered). A proper 1991–2020 climatology will be *worse* at
  overfitting daily wiggles, so the honest day-5 margin is likely somewhat larger.
- **Wind: UKMO loses to climatology beyond day 3** (skill −0.06 at day 4, −0.26 at
  day 5). Hourly 10 m wind at 5 days is basically unpredictable point-wise; "typical
  wind for this station and time of year" wins. This is the first genuinely
  publishable-shaped finding and worth a dashboard panel.
- Persistence degrades from 1.98 °C (24 h) to 3.03 °C (5 d) as expected;
  UKMO roughly halves persistence error at all leads.

## Live obs wiring (1 day of collection, tiny n — wiring check only)

Forecast/obs pairs already flow for every live truth source: land_obs temp
(n=99, MAE 0.74 °C, matching the ERA5-truth number), land_obs wind (MAE 1.13 m/s),
METAR temp (MAE 1.20 °C — integer-degree METAR temps add ~0.25 °C quantisation),
EA rain (63 pairs, no rain locally yet). Numbers are meaningless at this n; the point
is the joins work for all four sources. Revisit after ~4 weeks of collection.

## Decisions & caveats recorded

- `scores` library skipped: it drags xarray/pandas for metrics that are one-line
  closed forms. Hand-rolled in polars inside `wpq/metrics.py` (plan pre-authorised).
- `land_obs` wind units resolved: **m/s** (verified against co-located METAR kt→m/s
  at 8 airports, 2026-07-05). Recorded in `wpq/normalize.py` docstring.
- metrics.parquet stores sufficient statistics at
  (model, truth_source, variable, lead_day, station, month) grain; all report
  segmentation (nation, season, region) re-aggregates the sums. Never average MAEs.
- Rain forecast is deterministic {0,1} for now; Brier will become meaningful once
  MOGREPS member-fraction PoP lands (later chunk).
- Climatology baseline is in-sample — flagged above; upgrade path is a 1991–2020
  normal or a held-out split.
