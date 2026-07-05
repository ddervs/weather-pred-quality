# Prior art: who already does this, and what we can reuse

> **Archive.** Research-phase snapshot, kept verbatim. Note: the `scores`/MAPIE reuse
> verdicts below were later reversed — metrics are hand-rolled in polars
> (see [`docs/methodology.md`](../methodology.md)).

Research date: 2026-07-03. Bottom line: **nothing open-source does "UK multi-source live
forecast verification with calibrated probabilities"** — the niche is genuinely open — but
several components are reusable wholesale, and two projects prove the concept.

## Direct precedents (proof the idea works)

### ForecastAdvisor / ForecastWatch (forecastadvisor.com) — the commercial original
- Running since 2004; compares major providers at 2,200+ locations (US-centric, some
  international) on 1–3-day high/low temperature and precipitation (icon + text), scored
  against QC'd station observations; forecasts collected daily from provider websites/APIs
  at randomised times.
- Everything of value (scores, methodology detail, history) is **proprietary**; the free
  site shows only headline percentages. UK city coverage exists but is thin.
- Lesson to steal: equal-weight simple metrics + a public "who's best here?" widget is
  compelling; also their randomised-collection-time trick to avoid sampling bias.

### University of Reading rolling comparison (Thompson & Mammatt, 2024–) — the UK precedent
- Compares BBC Weather vs Met Office **apps** against the university's own observatory,
  hourly collection, verified every 3 h, up to 6-day lead; rolling results updated every 3 h
  on the Dept. of Meteorology site. Press: Met Office better on temperature, BBC slightly
  better on rain, both **over-forecast rain** ("rain bias" made national news).
- Single location (Reading), two providers, **no published code or raw data**, and the
  live page moved/404s (news article from Jan 2025 links a dept page that no longer resolves).
- Lesson: exactly our project at n=1 location. Their framing (usefulness %, not RMSE) is
  good communication. Worth emailing Dr Rob Thompson — likely friendly, may share
  methodology; our multi-location version is a natural extension. (Contact idea, not done.)

## Reusable evaluation machinery

| Project | What it is | Reuse verdict |
|---|---|---|
| **WFRT `verif`** (github.com/WFRT/verif) | Mature CLI for point-forecast verification: feed it a NetCDF/text of (obs, fcst, lead, location, time), get MAE/RMSE/ETS/reliability/etc. plots with aggregation by lead/location/time. BSD. | **Highest reuse potential.** Our pipeline could literally output verif-format files and get a full verification suite for free. Not a web dashboard though — matplotlib output. |
| **`scores`** (BoM, Australia) | Modern pandas/xarray metrics library: CRPS (ensemble + CDF), Brier, FIRM, Murphy diagrams, isotonic reliability, ~all of Jolliffe & Stephenson. Actively maintained, JOSS paper 2024. | **Use as the metrics engine.** Cleaner and broader than xskillscore. |
| **xskillscore / properscoring / climpred** | xarray metrics; climpred is initialised-ensemble-centric (climate timescales). | Fallback/supplement to `scores`. |
| **uncertainty-calibration** (pip; p-lambda/verified_calibration) | The exact Kumar–Liang–Ma "Verified Uncertainty Calibration" code: debiased calibration-error estimators + scaling-binning recalibrator + bootstrap CIs. | **Use for the calibration layer** on PoP-style probabilities. |
| **MAPIE / crepes** | Conformal prediction libraries (sklearn-style). MAPIE covers split + adaptive conformal for regression. | Use for conformal intervals on temperature/wind. |
| **WeatherBench 2** (google-research) | Gridded global benchmark of data-driven models vs ERA5; open evaluation code + cloud datasets; the public leaderboard site. | Different scope (global grids, research models, ERA5-as-truth). Steal metric implementations + headline-metric selection; not a base to build on for point/consumer verification. |
| **METplus (NOAA/DTC)** | The operational-centre verification suite. Extremely capable, extremely heavyweight (containers, config sprawl). | Skip for v1; know it exists. |
| **ForecastOps** (Parisi-Labs) | Local-first forecast eval: Parquet artifacts + DuckDB + static HTML reports. Generic (not weather-specific). | Not a dependency, but **its architecture (Parquet → DuckDB → static reports) is exactly the pattern** proposed in doc 04. |
| **Open-Meteo itself** | Ingests/normalises ~all national models, archives previous runs, free API, AGPL, self-hostable. | Already reused — it *is* our data layer. Their Substack posts on previous-runs are the methodology reference. |

## Adjacent/inspiration

- **Reading/Which? app-accuracy journalism (2025)**: public appetite for exactly this
  output; also a warning that "accuracy" claims get scrutinised — publish methodology.
- **ForecastWatch annual reports**: rank providers globally (IBM/The Weather Company wins
  repeatedly) — useful as the "who claims what" baseline.
- **emos/EMOS & Rasp-Lerch neural post-processing literature**: once we have cached
  forecast–obs pairs, post-processing (making our *own* better-calibrated forecast) is a
  natural phase 3; the same dataset powers it.
- **Carbon Intensity API dashboard culture** (UK grid): a model for how a small, free,
  well-designed UK public-data dashboard becomes infrastructure. North-star vibes.

## Gap analysis → our niche

| Capability | ForecastAdvisor | Reading study | WeatherBench2 | **Us (proposed)** |
|---|---|---|---|---|
| UK-wide, many locations | partial | ✗ (n=1) | grid but global/ERA5 | ✅ |
| Multiple providers incl. consumer apps | ✅ (closed) | 2 | ✗ (research models) | ✅ |
| Lead-time-stratified skill | ✅ (closed) | ✅ | ✅ | ✅ |
| Probabilistic metrics (CRPS/Brier/reliability) | ✗ (public side) | ✗ | ✅ | ✅ |
| Calibration / conformal guarantees | ✗ | ✗ | ✗ | ✅ ← differentiator |
| Open data + open code | ✗ | ✗ | ✅ | ✅ ← differentiator |
| Live map dashboard | ✗ | ✗ | leaderboard only | ✅ (north star) |

No one occupies the "open, UK, probabilistic, calibrated" cell. The Reading study proves
demand; Open-Meteo removes the hard data-engineering; `scores` + `verif` +
`uncertainty-calibration` + MAPIE remove the metrics work. What's genuinely novel here is
the **assembly + the calibration/conformal layer + the public map**.
