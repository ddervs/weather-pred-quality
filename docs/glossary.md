# Glossary

Every acronym and term of art used in this repo, in plain English. Grouped by theme.

## Organisations & weather models

- **NWP** — Numerical Weather Prediction: forecasting by running a physics simulation of
  the atmosphere on a supercomputer. "The model" in this repo always means an NWP model.
- **UKMO** — the UK Met Office (UK Meteorological Office). Also shorthand for its NWP
  models, which are what v1 verifies.
- **UKV** — the Met Office's high-resolution (~2 km grid) model covering the UK. Sharper
  local detail, shorter horizon.
- **UKMO global** — the Met Office's ~10 km whole-Earth model, used for longer leads.
- **`ukmo_seamless`** — Open-Meteo's blend of the two above: UKV near-term, global
  further out. The forecast stream this project scores.
- **MOGREPS** — Met Office Global and Regional Ensemble Prediction System: the UKMO
  model run ~18 times with perturbed starting conditions to express uncertainty.
  MOGREPS-G = global, MOGREPS-UK = high-res UK. We collect
  `ukmo_global_ensemble_20km` via Open-Meteo.
- **ECMWF** — European Centre for Medium-Range Weather Forecasts. Runs the **IFS**
  (Integrated Forecasting System, the leading global model), the **ENS** (its 51-member
  ensemble), and produces **ERA5**. A planned future comparison model.
- **ICON / GFS / AROME** — the German (DWD), US (NOAA) and French (Météo-France) NWP
  models. Future comparison candidates, all already exposed by Open-Meteo.
- **DWD / NOAA** — the German and US national weather services.

## Data sources & APIs

- **Open-Meteo** — free, keyless API that ingests most national NWP models and re-serves
  them per point. Our forecast data layer. Non-commercial use, CC-BY attribution.
- **Previous Runs API** — Open-Meteo endpoint archiving what each model predicted at
  fixed lead offsets (`*_previous_day1..7`), back to ~Jan 2024. Made the 2.5-year
  backfill possible.
- **ERA5** — ECMWF Re-Analysis v5: a **reanalysis**, i.e. a physics model re-run over
  the past with all real observations blended in. The best gridded estimate of what
  actually happened; used as interim ground truth for the backfill period. Caveat: it is
  still a model.
- **reanalysis** — see ERA5: hindsight-optimal model reconstruction of past weather.
- **DataHub** — the Met Office's API platform (datahub.metoffice.gov.uk). We use its
  **Land Observations** product (free tier, 360 calls/day, key required).
- **land obs** — hourly readings from ~150 Met Office surface weather stations:
  temperature, wind, humidity, visibility, pressure, weather code. No rain amounts on
  the free tier.
- **EA** — Environment Agency (England). Its flood-monitoring API exposes ~thousands of
  tipping-bucket rain gauges: 15-minute rainfall amounts in mm. Our rain-amount truth
  for England.
- **SEPA** — Scottish Environment Protection Agency: the Scottish equivalent of the EA.
  ~380 rain gauges, 15-minute mm totals, keyless, via a **KiWIS** API (the query
  protocol of KISTERS' water-data platform, used by many hydrology agencies) at
  `timeseries.sepa.org.uk`. Wired in 2026-07-05 as `sepa_rain` — rain-amount truth for
  all 6 Scottish stations.
- **NRW** — Natural Resources Wales, the Welsh equivalent. Open data but needs a free
  account/subscription key from their API portal; not yet wired in (pending sign-up).
- **METAR** — the standard aviation weather report format, issued ~half-hourly by
  airports. Fetched keyless from NOAA. **ICAO code** — the 4-letter airport identifier
  in a METAR (Heathrow = `EGLL`).
- **weather code / `wxString`** — coded "present weather" descriptions (Met Office
  integer codes; METAR strings like `RA` = rain, `DZ` = drizzle, `SHRA` = rain showers).
  Our rain-occurrence signal where amounts are unavailable.
- **geohash** — a short string encoding a lat/lon rectangle (e.g. `gcqf99`). The Met
  Office identifies land-obs stations by geohash, so it's the station ID everywhere in
  this repo.
- **OGL** — Open Government Licence, the permissive UK public-data licence (covers EA
  data). **CC-BY** — Creative Commons Attribution licence (Open-Meteo). **AGPL** — the
  copyleft licence of Open-Meteo's server code. **ToS / T&Cs** — terms of service.

## Forecast concepts

- **init time** — when a model run started (was *initialised*); the moment the forecast
  was "made". **valid time** — the hour the forecast is *about*.
- **lead time** — `valid_time − init_time`: how far ahead the forecast looks. "Day-3
  temperature MAE" = error of temperature forecasts made ~3 days in advance. Stored as
  `lead_hours` / `lead_days`.
- **deterministic forecast** — a single best-guess number per hour.
- **ensemble** — many parallel model runs from perturbed starts; the spread of
  **members** expresses uncertainty. **control (member 0)** — the unperturbed run.
- **PoP** — Probability of Precipitation. From an ensemble: the fraction of members
  predicting rain.
- **00Z / 12Z** — model runs initialised at 00:00 / 12:00 UTC ("Z" = Zulu = UTC). The
  main synoptic cycle times.
- **backfill** — retrieving historical forecasts (via the Previous Runs API) instead of
  having cached them live.
- **persistence** — the "no-skill" baseline forecast: tomorrow's weather = today's.
- **climatology** — the other baseline: the long-run average for that place, day of
  year and hour ("typical mid-July 3 pm in Leeds").
- **synoptic** — weather at the scale of whole pressure systems (~1000 km); "the error
  is synoptic, not local" = everyone's error comes from misplacing the big systems.
- **JJA / DJF / MAM / SON** — the meteorological seasons by month initials
  (June-July-August = summer, etc.).

## Verification metrics

- **MAE** — Mean Absolute Error: average size of the miss, in natural units ("typically
  off by 1.2 °C"). Our headline for temperature and wind.
- **bias** — mean signed error: systematic over/under-forecasting.
- **RMSE** — Root Mean Square Error: like MAE but punishes big misses harder.
- **contingency table** — the 2×2 count of hit / miss / false alarm / correct negative
  for a yes/no event like "rain this hour".
- **POD** — Probability of Detection (hit rate): what fraction of real rain hours were
  forecast.
- **FAR** — False Alarm Ratio: what fraction of forecast rain hours stayed dry.
- **CSI** — Critical Success Index: hits / (hits + misses + false alarms).
- **ETS** — Equitable Threat Score: CSI corrected for chance hits. Standard headline
  rain score at met centres; 0 = no skill, 1 = perfect.
- **base rate** — how often the event happens at all (~23 % of UK hours have rain).
- **Brier score** — mean squared error of a probability forecast of a binary event.
- **Murphy decomposition** — Brier = **reliability** (do stated probabilities match
  reality? lower = better) − **resolution** (does the forecast separate rainy from dry
  situations? higher = better) + **uncertainty** (the weather's inherent variance).
- **skill score (SS)** — `1 − score/score_baseline`: how much better than a baseline;
  0 = no better, negative = worse.
- **CRPS** — Continuous Ranked Probability Score: generalises MAE to full probability
  distributions, letting deterministic and ensemble forecasts be compared on one number.
  Planned, not yet implemented.
- **reliability diagram** — plot of stated probability vs observed frequency ("when it
  says 60 %, it rains 48 % of the time"). Arrives with PoP data.
- **calibration** — the property that stated probabilities/intervals match observed
  frequencies. **sharpness** — how narrow/decisive the forecasts are. The goal is
  maximal sharpness *subject to* calibration.

## Statistics & guarantees

- **conformal prediction** — distribution-free method turning point forecasts into
  intervals with guaranteed coverage. **split conformal** — the simple variant: measure
  errors on a held-out calibration set, use their quantile **q̂** as the interval
  half-width.
- **coverage** — fraction of intervals that contain the truth (target here: 90 %,
  `alpha` = 0.1).
- **nonconformity score** — the error measure conformal ranks (here |forecast − obs|).
- **Mondrian conformal** — separate conformal calibration per group (here
  nation × lead), so the guarantee holds within each segment.
- **exchangeability** — the assumption conformal needs (past and future errors
  interchangeable); technically violated by weather's serial correlation — hence we
  *monitor* coverage.
- **bootstrap** — estimating uncertainty by resampling the data many times. **block
  bootstrap** — resampling whole blocks (here station-days) to respect correlation
  within a block. **CI** — confidence interval.
- **in-sample** — evaluated on the same data used to fit/compute it (flattering);
  **out-of-sample / held-out** — evaluated on data not used for fitting (honest).
- **sufficient statistics** — the sums/counts from which a metric can be exactly
  recomputed for any aggregation (store `sum_abs_err` and `n`, derive MAE at any grain).

## Tooling

- **Parquet** — compressed columnar file format for tables; what all processed data is
  stored in. **polars** — the dataframe library doing the processing. **DuckDB** — SQL
  engine that queries Parquet directly (currently unused; candidate for removal).
- **uv** — the Python package/environment manager (`uv sync`, `uv run …`).
- **GitHub Actions** — CI service running the collector (every 6 h) and the weekly
  metrics rebuild; "git-scraping" = committing fetched data straight into the repo.
