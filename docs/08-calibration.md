# 08 — Calibration layer: conformal intervals, Brier decomposition, bootstrap CIs

*2026-07-05. Produced by `wpq/calibration.py` (via `scripts/run_calibration.py`) →
`data/metrics/{conformal,brier_decomposition,bootstrap_ci}.parquet`. Sample: UKMO
`prev_runs` backfill vs ERA5 truth, 33 stations. Conformal is hand-rolled split
conformal (no MAPIE — same no-heavy-deps call as `scores`).*

## Conformal temperature intervals: coverage holds out-of-sample

Split conformal, Mondrian-grouped by **nation × lead**, nonconformity = |error|,
calibrated on **2024 only**, scored on **2025-01 → 2026-06** (clean temporal split).

90 % interval half-widths (± °C) and their test coverage (target 0.90):

| lead (d) | UK ±q̂ | UK coverage | England | Scotland | Wales | N. Ireland |
|---|---|---|---|---|---|---|
| 0 | 1.5 | 0.906 | 0.920 | 0.890 | 0.910 | 0.880 |
| 1 | 1.7 | 0.889 | 0.890 | 0.891 | 0.899 | 0.887 |
| 2 | 2.4 | 0.920 | 0.920 | 0.925 | 0.925 | 0.918 |
| 3 | 2.6 | 0.912 | 0.908 | 0.905 | 0.924 | 0.913 |
| 4 | 3.0 | 0.905 | 0.904 | 0.915 | 0.893 | 0.885 |
| 5 | 3.6 | 0.903 | 0.901 | 0.916 | 0.897 | 0.903 |

- **Every cell lands within ±0.03 of nominal** despite the calibration year (2024)
  and scoring period (2025–26) being different climate samples. Split conformal on
  a year of data is enough for honest UK temperature intervals — this is the
  guarantee the north star needs.
- The interval story for a user: "tomorrow's forecast is trustworthy to ±1.7 °C,
  the day-5 forecast only to ±3.6 °C" — same information as MAE but stated as a
  guarantee rather than an average.
- Scotland needs the widest short-lead intervals (±1.8 vs ±1.4–1.5 °C at day 0),
  consistent with the MAE story in docs/07; nations converge by day 2.
- Half-widths quantise to 0.1 °C because Open-Meteo serves 0.1 °C-resolution temps.

## Rain: the binary forecast is *worse than climatology* beyond day 1 (Brier)

Murphy decomposition, `brier = reliability − resolution + uncertainty`
(reliability: lower = better; resolution: higher = better):

| lead (d) | Brier | reliability | resolution | uncertainty | Brier skill vs base rate |
|---|---|---|---|---|---|
| 0 | 0.153 | 0.025 | 0.050 | 0.178 | **+0.14** |
| 1 | 0.170 | 0.032 | 0.034 | 0.172 | **+0.01** |
| 2 | 0.192 | 0.049 | 0.035 | 0.177 | **−0.08** |
| 3 | 0.223 | 0.067 | 0.025 | 0.182 | **−0.23** |
| 4 | 0.243 | 0.082 | 0.017 | 0.178 | **−0.36** |
| 5 | 0.260 | 0.095 | 0.010 | 0.175 | **−0.49** |

Headline finding: **as a probability statement, a hard yes/no rain forecast is worse
than just quoting the climatological base rate (~23 %) from day 2 out** — resolution
collapses (0.050 → 0.010) while the reliability penalty of overconfident 0/1 claims
balloons (0.025 → 0.095). The ETS story in docs/07 showed the forecast still has
*discrimination* skill at day 5 (ETS 0.13 > 0); the Brier story shows that skill is
destroyed by packaging it as certainty. This is the strongest possible motivation for
MOGREPS member-fraction PoP (unlocks ~2026-08-01) — same decomposition code will then
produce real multi-bin reliability curves.

## Bootstrap CIs: every lead-to-lead difference is real

95 % CIs, block bootstrap over **station-days** (B = 1000, fixed seed; iid-hour
resampling would understate widths — hours within a station-day are correlated):

temp MAE (°C): 0.701 [0.697, 0.705] → 1.631 [1.616, 1.645] across leads 0→5.
rain ETS: 0.343 [0.339, 0.346] → 0.133 [0.128, 0.137].

CIs are ±0.005–0.015 — with ~700 k pairs per lead every headline difference in
docs/07 is comfortably significant. The odd non-monotone step (ETS lead 1 → 2:
0.272 → 0.284) is also significant, confirming it as the sample-composition artefact
of previous-runs null patterns (docs/07 caveat), not noise.

## Caveats

- Conformal exchangeability is technically violated (serial correlation, climate
  drift); the observed coverage stability is an empirical result, not a theorem.
  Station-day-blocked conformal or weekly recalibration is the upgrade if drift
  appears — monitor the coverage column when the weekly CI job refreshes this.
- Everything above is vs **ERA5 truth** (model-space). Repeating vs station obs
  (land_obs/EA/METAR) once a few months of live data accumulate is the credibility
  check — ERA5 flatters the model at stations where reanalysis and model share biases.
- Brier decomposition currently has two bins (p ∈ {0,1}); "reliability" then just
  measures the miss/false-alarm rates of each claim, which is why it can be read as
  overconfidence. Curves become meaningful with PoP.
