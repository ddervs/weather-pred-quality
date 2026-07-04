# Metrics, calibration, and the reliability score

How we'd actually score forecasts, in three layers: classic verification, probabilistic
verification, and calibration/conformal (the differentiator). Then options for a single
"reliability score". Everything here has a maintained Python implementation — no metric
needs writing from scratch.

## Layer 1 — deterministic verification (day one)

Per (source/model, variable, lead time, location, month):

- **Temperature/wind**: MAE, RMSE, bias (mean error). MAE is the headline (robust,
  explainable: "typically off by 1.3 °C at 3 days").
- **Precipitation occurrence** (threshold, e.g. ≥0.2 mm/h): contingency-table scores —
  hit rate (POD), false-alarm ratio (FAR), CSI, and **Equitable Threat Score (ETS)** as the
  headline (standard at met centres, corrects for chance).
- **Precipitation amount**: MAE on amounts is dominated by zeros; use categorical buckets
  (0.2/1/4 mm h⁻¹) with ETS per bucket, or SEEPS if we get ambitious.
- **Baselines — non-negotiable**: every score is only meaningful as a *skill score* vs
  (a) **persistence** (tomorrow = today) and (b) **climatology** (ERA5 1991–2020 for that
  station/day-of-year). "Beats climatology at day 6" is the real question. Skill score
  `SS = 1 − score/score_baseline`.

## Layer 2 — probabilistic verification

- **Brier score** for probability forecasts of binary events (PoP is the canonical case),
  with the **Murphy decomposition** BS = reliability − resolution + uncertainty. Sources
  publishing PoP: Open-Meteo derived probabilities, Met Office (app shows %), OWM. For
  ensemble sources, PoP = member fraction exceeding threshold.
- **CRPS** for full distributions (from ensemble members; `scores` and properscoring have
  the fair-ensemble estimator). Generalises MAE: CRPS of a deterministic forecast = MAE,
  so **deterministic and ensemble sources are directly comparable on one number**. This is
  the single best headline metric for us.
- **Reliability diagrams** (forecast probability vs observed frequency, with bin counts) —
  the visual centrepiece the Reading study lacked. "When the app says 60 % rain, it rains
  48 % of the time" is the most shareable output this project can produce.
- **PIT histograms / rank histograms** for ensemble calibration (U-shape = underdispersed,
  the classic NWP failure).
- **Sharpness** (mean interval width) reported alongside calibration, per the
  Gneiting–Balabdaoui–Raftery principle: *maximise sharpness subject to calibration*.

## Layer 3 — calibration measurement & recalibration (the differentiator)

- **Verified Uncertainty Calibration (Kumar, Liang, Ma, NeurIPS 2019)** — directly usable
  via `pip install uncertainty-calibration`:
  - Their point: binned ECE-style estimators *underestimate* miscalibration of continuous
    recalibrators (Platt/temperature scaling); they give debiased estimators + bootstrap CIs,
    and the **scaling-binning recalibrator** which is both sample-efficient and verifiable.
  - Application here: (a) *measure* each provider's PoP calibration error with honest CIs —
    this is the "reliability score" backbone; (b) *recalibrate* provider probabilities to
    produce our own calibrated layer (phase 3).
- **Conformal prediction** for continuous variables (temperature, wind):
  - Split/online conformal on top of any point forecast yields intervals with guaranteed
    coverage, no distributional assumptions. For time series under distribution shift, use
    **Adaptive Conformal Inference (Gibbs & Candès)** family; libraries: **MAPIE**, `crepes`.
  - Directly relevant recent work: *"Rigorous uncertainty quantification of probabilistic AI
    weather forecasts with conformal prediction"* (arXiv:2606.19642, June 2026) — applies
    online conformal to GenCast/NeuralGCM/AIFS-ENS temperature & precipitation, finds AI
    ensembles miscalibrated on extremes, fixes coverage with no cost to CRPS. Our project is
    the "consumer/NWP product" version of exactly this. Also: in-sample conformal calibration
    (arXiv:2503.03841) connects recalibration and conformal guarantees.
  - Conditional coverage caveat: marginal coverage ≠ coverage per region/lead/season. Use
    Mondrian/group-conditional conformal (groups = region × lead bucket) — this fits the
    segmentation model of the dashboard perfectly.
- **Post-processing (phase 3+)**: EMOS/NGR, quantile regression, NGBoost, Rasp–Lerch-style
  neural post-processing. The cached forecast–obs dataset is exactly the training data. This
  is how the north-star map gets probabilities *better* than any single source.

## Library choices (all pip-installable, maintained)

| Need | Library | Notes |
|---|---|---|
| CRPS, Brier, ETS, reliability, Murphy diagrams | **`scores`** (BoM) | broadest, pandas/xarray, JOSS 2024 |
| Calibration error with CIs, scaling-binning | **`uncertainty-calibration`** | the Kumar–Liang–Ma code |
| Conformal (split, adaptive, Mondrian-ish) | **MAPIE** | sklearn-style |
| Plot-everything CLI for sanity checks | **WFRT `verif`** | feed it our data, free plots |
| Reliability diagrams, PIT | `scores` + matplotlib | trivial |

## Designing "the reliability score" (options, not a decision)

One number per provider (per region/lead/variable segment). Candidates:

1. **CRPS skill score vs climatology** (`1 − CRPS/CRPS_clim`), averaged over variables with
   fixed weights. Pro: proper, comparable across variables/sites, handles deterministic and
   probabilistic uniformly. Con: less intuitive to the public.
2. **ForecastAdvisor-style "% correct"** composite (temp within ±1.7 °C, rain yes/no hit).
   Pro: instantly explainable. Con: improper, arbitrary thresholds, gameable.
3. **Two-axis score**: *accuracy* (CRPS-SS) × *honesty* (calibration error with CI, from
   uncertainty-calibration). Publish both; the "honesty" axis is our novelty. A provider can
   be accurate-but-overconfident (classic app rain bias) and users deserve to see that.
4. **Elo-style pairwise**: providers "play" each forecast-obs pair; proper-score winner takes
   Elo points. Pro: robust to missing data (not every provider covers every site/lead);
   fun leaderboard dynamics. Con: nonstandard in meteorology, harder to defend academically.

Recommendation to discuss: **publish (1) as the scientific score and (3)'s honesty axis
beside it; add (2) as a tooltip translation** ("in plain terms: right about rain 78 % of
the time"). Avoid (4) initially.

## Segmentation model (drives schema + dashboard)

Every metric computed over cells of:
`provider/model × variable × lead bucket (0–24 h, 24–48, …, 120+) × region (UK nations + English regions) × season × event-severity bucket`
with minimum-sample-size rules (hide cells with n < ~100; show CIs everywhere — bootstrap
over days, not hours, because errors are serially correlated within a day).
