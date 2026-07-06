# Data sources: what we collect, and what counts as truth

*Living doc. Last updated 2026-07-05. Covers only sources actually wired into the
codebase. Everything ever considered (met.no, OpenWeatherMap, BBC, gridded ECMWF…) is in
[research/01-data-sources.md](research/01-data-sources.md).*

Verification needs two kinds of data, and they come from different places:

1. **Forecasts** — what a weather model *predicted* would happen at a place and time.
2. **Observations ("ground truth")** — what *actually* happened there, measured by
   instruments.

A forecast–observation pair for the same place and hour, tagged with how far in advance
the forecast was made (the **lead time**), is the atom of this whole project.

---

## 1. Forecast sources

All v1 forecasts are the **UK Met Office's numerical weather prediction (NWP) model**,
accessed through [Open-Meteo](https://open-meteo.com) — a free, keyless,
non-commercial-use API that ingests most national weather models and re-serves them per
point. Open-Meteo's `ukmo_seamless` model is the **raw Met Office model output** (the
2 km UKV model over the UK, blended with the ~10 km UKMO global model further out), *not*
the post-processed product shown in the Met Office app. That distinction matters:
we are currently scoring the *engine*, not the *product*. (The app-like product is a
planned v1.5 add via Met Office DataHub — see [PLAN.md](PLAN.md).)

Three Open-Meteo endpoints are in use:

### 1a. Live forecasts (`api.open-meteo.com/v1/forecast`) → `data/raw/ukmo_forecast/`

Fetched every 6 h by the collector for all 33 stations in one call. Hourly values, ~8-day
horizon, 9 variables: `temperature_2m`, `precipitation`, `rain`, `snowfall`,
`wind_speed_10m`, `wind_gusts_10m`, `wind_direction_10m`, `cloud_cover`,
`relative_humidity_2m`. (The normaliser currently uses temperature, precipitation, wind
and gusts; the rest are cached for later.)

Known wart: the payload does not state when the model run was *initialised*, so lead time
is approximated as `valid_time − fetch_time`. Good enough at a 6 h cadence.

### 1b. Ensemble forecasts (`ensemble-api.open-meteo.com`) → `data/raw/ukmo_ensemble/`

**MOGREPS** is the Met Office's ensemble system: the model is run ~18 times from slightly
perturbed starting conditions, and the spread of the members expresses forecast
uncertainty. The fraction of members predicting rain is a real probability-of-
precipitation (PoP) — the raw material for the calibration side of this project.

Fetched ~2/day — whenever the previous ensemble file is ≥10 h old, bounding repo
growth without trusting GitHub's cron punctuality (a wall-clock-hour gate never
fired: scheduled runs arrive hours late; caught 2026-07-06) — 3 variables
(`temperature_2m`, `precipitation`, `wind_speed_10m`), all members
(`ukmo_global_ensemble_20km`, member 0 = control).

**Why this must be cached live**: Open-Meteo keeps no archive of past ensemble runs.
Every missed run is unrecoverable — this is the one source that genuinely needs the
collector to be reliable. Meaningful PoP verification unlocks ~4 weeks after collection
started (≈ 2026-08-01).

### 1c. Previous Runs (`previous-runs-api.open-meteo.com`) → `data/backfill/prev_runs/`

The key discovery of the research phase. Open-Meteo archives what each model predicted at
fixed lead offsets — `temperature_2m_previous_day1` is what was forecast ~24 h before
each valid hour, up to `previous_day7` — **back to ~January 2024**. This provided ~2.5
years of lead-stratified UKMO forecasts *before our collector existed*, which is what all
current results are computed from (leads 0–5 days, backfilled once by
`scripts/backfill_ukmo.py`).

Caveats baked into all downstream analysis:

- Lead granularity is **daily** (no sub-daily init times), deterministic runs only.
- **Leads ≥ 1 day have holes**: 25–45 % of hours come back null, and the missing subset
  differs per lead — so metric comparisons *across* leads carry a sample-composition
  caveat (see [results/2026-07-05-first-real-metrics.md](results/2026-07-05-first-real-metrics.md)).
- Lead 0 arrives under the plain variable name (`temperature_2m`), not
  `_previous_day0`.

---

## 2. Ground truth — what we verify against, and why

There is no single perfect "truth" source for UK weather; each instrument network
measures some things well and others not at all. The strategy (standard WMO-style
practice) is: **verify at observation stations, using the best instrument for each
variable**, rather than interpolating either side.

| Source | What it's trusted for | Cadence | The catch |
|---|---|---|---|
| **Met Office land observations** (`land_obs`) | temperature, wind, humidity, visibility, pressure; rain *occurrence* via weather code | hourly | **no rain amounts** on the free tier; needs an API key (360 calls/day); some listed stations are duds |
| **Environment Agency rain gauges** (`ea_rain`) | rain **amounts** (mm, tipping-bucket) | 15 min | **England only**; gauges go dormant; occasional garbage readings (QC'd at normalisation) |
| **SEPA rain gauges** (`sepa_rain`) | rain **amounts** (mm, tipping-bucket) — **Scotland's** equivalent of `ea_rain` | 15 min | Scotland only; same dormancy/QC caveats as EA (identical treatment at normalisation) |
| **NRW rain gauges** (`nrw_rain`) | rain **amounts** (mm, tipping-bucket) — **Wales's** equivalent | 15 min | Wales only; needs the free `NRW_API_KEY`; station "Online" status lies — liveness comes from `latestTime` |
| **METAR airport reports** (`metar`) | temperature, wind — as an independent cross-check | ~30 min | integer °C only; no rain amounts (occurrence codes only); airports ≠ towns |
| **ERA5 reanalysis** (`era5`) | *everything*, as interim truth for the 2024–26 backfill | hourly, ~5-day lag | it is itself a **model** product — see below |

**Why ERA5 as interim truth?** ERA5 is ECMWF's "reanalysis": a physics model run over the
past with all available observations assimilated in — the best gridded estimate of what
the atmosphere actually did, available everywhere, back decades. Our live observation
collection only started 2026-07-04, but the forecast backfill reaches to 2024-01; ERA5 is
the only truth source covering that span. The cost: ERA5 is model-space truth — it
smooths local extremes and can share biases with the forecast model being scored
(flattering it). **Every current headline number is vs ERA5**; re-running against real
station observations once a few months accumulate is the standing credibility check
(see [PLAN.md](PLAN.md)).

Rain occurrence conventions (the "did it rain this hour?" event) differ per source and
are defined precisely in [data-layout.md](data-layout.md).

---

## 3. The 33 stations — and how coverage differs by region

Verification locations are **fixed** and anchored at instruments, not city centres:
`scripts/build_station_registry.py` seeded ~35 UK cities, found each one's nearest
healthy Met Office land-obs station (≥40 of 48 hourly entries reporting temperature),
and pinned the location to the *station's* coordinates. Stations are never moved
casually — continuity of the time series is the point.

Each location is a **station bundle**:

1. the Met Office land-obs station (identified by a 6-character **geohash**, e.g.
   `gfnmmy` — this geohash is the station ID throughout the codebase),
2. the nearest *live* EA rain gauge (England only),
3. the nearest *live* SEPA rain gauge (Scotland only; added 2026-07-05 by
   `scripts/add_sepa_gauges.py`, carrying the pre-resolved KiWIS `ts_id`),
4. the nearest *live* NRW rain gauge (Wales only; added 2026-07-05 by
   `scripts/add_nrw_gauges.py`, carrying the per-station rainfall `parameter` ID),
5. the nearest METAR airport within 40 km (where one exists).

Current registry (`data/stations.json`, built 2026-07-04): **33 stations — 23 England,
6 Scotland, 2 Wales, 2 Northern Ireland.** Interactive map:
[station-map.html](station-map.html).

Coverage is **not uniform**, and this shapes what can be verified where:

- **Rain amounts**: **31 of 33 stations** (since 2026-07-05) — 24 with an EA gauge
  (England plus one Welsh station), all **6 Scottish stations via SEPA gauges**
  (nearest live gauge 0.2–14.1 km; Edinburgh's is Gogarbank, 200 m from the Met
  Office station), and both **Welsh stations via NRW gauges** (Bangor→Llyn Cefni
  3.2 km, Cardiff→Llantwit Major 4.5 km). The NRW pairing also fixes a quiet wart:
  Cardiff's "EA" gauge is 22.6 km away **across the Bristol Channel in Somerset** —
  it is kept for continuity, but `nrw_rain` is the credible rain truth there.
  Still without rain-amount truth: **the two NI stations** (no free gauge API found).
- **METAR cross-check**: 25 of 33 stations have a paired airport; 8 don't.
- **Temperature/wind**: all 33 stations (that's the health-check criterion).
- Each station carries `country` (the four UK nations — the main regional segmentation
  in results) and `region` (Met Office area code, e.g. `se`, `yh`, `gr`) from the Met
  Office station metadata.
- London quirk: the central-London station (`gcpvj0`) returns empty records, so London
  is anchored by Heathrow and Greenwich instead.

Forecast data itself is uniform across stations (Open-Meteo serves every point
identically); it is the *truth* side that varies regionally. Model *skill* also varies
regionally — Scotland is hardest at short leads (terrain) — but that's a finding, not a
coverage artefact; see [results/](results/).

---

## 4. Usage limits and terms (why the design looks like this)

All free, all within ~10× headroom at current volumes
(full cost research: [research/05-costs.md](research/05-costs.md)):

| Source | Limit | Our usage | Terms |
|---|---|---|---|
| Open-Meteo (all endpoints) | 10k calls/day, non-commercial | ~20–40/day | CC-BY 4.0 attribution; AGPL self-host escape hatch |
| Met Office Land Obs | **360 calls/day** (the binding constraint) | ~130/day (33 stations × 4 runs) | DataHub T&Cs: derived metrics publishable, raw feeds not redistributable |
| EA flood-monitoring | fair use, keyless | ~130/day | Open Government Licence |
| SEPA KiWIS time series | fair use, keyless | 4/day (all gauges per call) | Open Government Licence, attribute SEPA |
| NRW rivers-and-seas | fair use; free subscription key (`NRW_API_KEY`, `Ocp-Apim-Subscription-Key` header) | 8/day (one per gauge per run) | open data via [api-portal.naturalresources.wales](https://api-portal.naturalresources.wales) |
| NOAA METAR | ≤100 req/min, keyless | 4/day | public domain |

Conventions: identifying User-Agent everywhere (`wpq/config.py`); the Met Office and
NRW keys live in `.env` / Actions secrets and are never committed or logged.
