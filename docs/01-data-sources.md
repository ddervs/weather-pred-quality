# Data sources for UK forecast verification

Research date: 2026-07-03. All limits/prices checked against provider pages on this date.

Two distinct things we might verify, and they need different sources:

1. **Raw NWP models** (UKMO's UKV, ECMWF IFS/AIFS, DWD ICON, NOAA GFS, Météo-France AROME…) —
   what the atmosphere-simulation engines say. Almost entirely solved by Open-Meteo.
2. **Consumer forecast products** (Met Office app/website, BBC Weather, Apple Weather,
   AccuWeather…) — post-processed, blended, human-influenced products people actually see.
   These need per-provider APIs, and some (BBC) have no official API at all.

Both are interesting: "which model is best" is the scientific question; "which app should I
trust" is the question the public actually asks (and what University of Reading studies).

---

## Tier 1 — free, keyless, ToS-friendly (probe-verified ✅)

### Open-Meteo — the workhorse

- **URLs**: `api.open-meteo.com/v1/forecast`, `previous-runs-api.open-meteo.com`,
  `ensemble-api.open-meteo.com/v1/ensemble`, `historical-forecast-api.open-meteo.com`,
  `archive-api.open-meteo.com` (ERA5)
- **Terms**: free for **non-commercial** use, no key, attribution CC-BY 4.0.
  Limits: <10,000 calls/day, 5,000/hr, 600/min. Our whole collector needs ~20–40 calls/day.
  Open source (AGPL server); could self-host if we ever outgrow the free tier.
- **Models exposed individually**: `ukmo_seamless` (UKV 2 km + global 10 km!), `ecmwf_ifs025`,
  `icon_seamless`, `gfs_seamless`, `meteofrance_seamless`, `metno_seamless`, `best_match`, more.
  Probe: all return full hourly data for UK points; multi-location + multi-model in one call.
- **Previous Runs API** — *the key find of this research*. Every variable is retrievable at
  fixed lead offsets (`temperature_2m_previous_day1` = what was forecast 24 h before valid
  time, … up to `previous_day7`), **archived back to ~January 2024** for most models.
  Consequences:
  - We can compute ~2.5 years of lead-time-stratified verification for ~7 models **today**,
    before any collector of our own exists.
  - Missed collector runs for Open-Meteo-sourced models are recoverable — the caching job's
    reliability requirement drops dramatically (see architecture doc).
  - Caveat: lead resolution is daily (24 h steps), sub-daily init times are not separately
    archived, and only the deterministic runs (not past ensembles) are covered.
- **Ensemble API**: raw members per point — MOGREPS-G (18), MOGREPS-UK (~3 exposed),
  ECMWF ENS (51), ICON-EU-EPS (40), GEFS. >100 members/location/hour. This is the raw
  material for CRPS, rank histograms, and calibrated probabilities. No archive of past
  ensemble runs on the free tier → **if we want ensemble verification history, we must cache
  ensembles ourselves from day 1** (the one thing that genuinely needs the collector).
- **Historical/ERA5 APIs**: observations-substitute and climatology baseline (see ground truth).
- Sizing (probed): ~81 KB raw (~13 KB gz) per location for 7 models × 11 vars × 8 days hourly.

### MET Norway (Yr) locationforecast 2.0

- **URL**: `api.met.no/weatherapi/locationforecast/2.0/complete`
- **Terms**: free worldwide, CC-BY 4.0, **mandatory identifying User-Agent** with contact
  info, must honour `Expires`/`If-Modified-Since` (probed: ~30 min expiry). No key.
- ~9-day horizon, hourly near-term. This is what Yr and many apps display — a genuine
  "consumer product" data point, and (per met.no docs) post-processed ECMWF+local blend.
- **Probe finding**: no `probability_of_precipitation` or percentile fields for UK points —
  deterministic only outside the Nordics. No archive → needs caching from day 1.

### METAR via NOAA aviationweather.gov (ground truth, partial)

- **URL**: `aviationweather.gov/api/data/metar?ids=EGLL,...&format=json`
- Keyless, ≤100 req/min, 15-day lookback. ~30 UK airports usable; 2 obs/hour.
- Good: temperature (integer °C), wind speed/dir/gust, pressure, visibility, present weather.
- **Bad: UK METARs report no precipitation amounts** — rain occurrence only via codes
  (`RA`, `SHRA`, `DZ`). Fine for "did it rain?" (Brier/PoP verification), useless for amounts.

## Tier 2 — free tier with signup (no key yet; signup documented)

### Met Office Weather DataHub — the UK reference

Signup is free (email + API key). Three relevant products:

| Product | Free tier | What it gives |
|---|---|---|
| **Site-specific Global Spot** | **360 calls/day** | Hourly / 3-hourly / daily forecasts for any point, up to ~14 days. Effectively the Met Office app's data. 360/day supports ~50 sites × 2 fetches/day × 3 products, or 40 sites × 8 fetches on one product. |
| **Land Observations** | **360 calls/day** | ~150 UK stations, hourly. **Probed 2026-07-04**: per-station calls (`/observation-land/1/{geohash}`), each returning 48 h of hourly data; station discovery via `/nearest?lat=&lon=` (coords ≤2 dp or HTTP 400). Parameters: temperature (0.01 °C), humidity, wind speed/gust/direction, visibility, mslp, pressure tendency, weather code. **No rainfall amounts** — occurrence only via weather code; amounts come from EA gauges (below). One station near central London returns empty records — health-check stations before adopting them. 50 stations × 1 call/day = 50 calls (48 h window gives full coverage with huge slack). |
| **Blended Probabilistic (IMPROVER)** | 30-day trial only (55 calls/day, 1 site) | Calibrated probabilistic site forecasts — exactly our north star, sold by the Met Office. Paid from £9/mo (550 calls/day). Worth a trial month later to benchmark our own calibration against theirs. |

Licensing: DataHub T&Cs; site-specific data is not Open Government Licence — attribution
and no-bulk-redistribution terms apply. Storing for internal verification + publishing
*derived metrics* is the standard pattern and appears fine; republishing raw feeds is not.
Action item: read the T&Cs properly at signup.

### OpenWeatherMap One Call 3.0/4.0

1,000 calls/day free, but requires an account **with a payment card on file** (pay-per-call
beyond free; a daily cap can be set to 1,000 to guarantee £0). Widely used by apps, so it's a
meaningful "consumer product" source. Moderate priority — add if card-on-file is acceptable.

### Others (optional extras, all free-tier-with-key)

- **Visual Crossing** — 1,000 records/day free; includes historical.
- **Tomorrow.io** — free tier (rate-limited); proprietary blend.
- **AccuWeather** — free tier is small (~50 calls/day); popular app, so interesting as a
  consumer product sample at low cadence.
- **Apple WeatherKit** — 500k calls/mo but needs Apple Developer Programme (£79/yr) — skip.
- **DWD, Météo-France, KNMI open data** — raw model output, already covered via Open-Meteo.

## Tier 3 — bulk/gridded (north-star phase, not needed now)

- **ECMWF Open Data**: IFS + AIFS (incl. AIFS-ENS) at 0.25°, CC-BY, GRIB2, rolling ~12-run
  window, mirrored free on AWS/Azure/GCP; `ecmwf-opendata` Python client. The path to a real
  UK *map* (grid, not points) and to ensembles straight from source. Engineering cost: GRIB
  handling, ~GBs/day if we keep full UK cutouts.
- **Met Office Atmospheric data on DataHub** (UKV/MOGREPS gridded): has a pricing page —
  free tier unclear/limited; enterprise-leaning. Also UKV/MOGREPS are on AWS Open Data as
  part of the (rebranded) Met Office ASDI datasets — worth checking current status if we go
  gridded.
- **MIDAS Open (CEDA)**: full historical UK station archive, free with academic-style
  registration, but ~1-year publication lag → for backtesting, not live verification.

## The BBC problem

BBC Weather is DTN/MeteoGroup-powered, and there is **no official public API**. The
community-known `weather-broker-cdn.api.bbci.co.uk` JSON endpoints are internal; scraping
them is a ToS grey zone (BBC ToU prohibit automated access outside their syndication terms).
Options, in increasing order of boldness:

1. **Skip BBC**; use met.no + Met Office + OWM as the consumer products. (Safe default.)
2. Ask the BBC/DTN for research access (long shot, but the Reading study demonstrates
   precedent for app-data research).
3. Low-volume scraping for personal research (what several hobby projects and arguably the
   Reading study do). Legally grey; your call, not made tonight.

## Ground truth strategy (the quiet hard problem)

Verification is only as good as the "truth". Options, best used in combination:

| Source | Cadence | Rain amounts? | Coverage | Catch |
|---|---|---|---|---|
| Met Office Land Obs API | hourly | ❌ (occurrence via weather code) | ~150 UK stations | 360 calls/day free; per-station calls, 48 h window; some dud stations (probed) |
| **EA flood-monitoring rain gauges** | **15 min** | **✅ (mm, tipping bucket)** | England, dense (14 gauges within 15 km of central London) | keyless, OGL; England only (SEPA=Scotland, NRW=Wales); dormant gauges exist; under-catch in wind/snow |
| METAR (NOAA, keyless) | 30 min | ❌ (occurrence only) | ~30 airports | integer °C; airports ≠ towns |
| ERA5(-Land) via Open-Meteo | hourly, ~5-day lag | ✅ (model) | everywhere | it's *reanalysis* — a model product; circularity risk when scoring ECMWF; smooths local extremes |
| MIDAS Open (CEDA) | hourly | ✅ | hundreds of stations | ~1 yr lag |

Recommended pattern (matches WMO practice): score each forecast point against the **nearest
qualifying station observation**, choose forecast points *at* station locations (i.e. our
"50 locations" should simply be 50 observation stations — airports + Met Office sites),
and use ERA5 only for gap-filling and climatology baselines. Deciding station list =
deciding location list; do this once, early, and never move them.

Post-probe refinement (2026-07-04): each location becomes a **station triple** — Met Office
land-obs station (temp/wind/humidity/visibility) + nearest healthy EA/SEPA/NRW rain gauge
(amounts) + METAR airport where available (cross-check). Health-check all three at
selection time and periodically thereafter.

## Variables worth tracking (v1 proposal)

- 2 m temperature (hourly) — everyone's headline metric, cleanly observed.
- Precipitation: occurrence (PoP verification) + amount buckets (0.2/1/4 mm hr⁻¹) — the UK question.
- 10 m wind speed + gusts — observed well at airports.
- Cloud cover (okta buckets) — observed at stations, notoriously badly forecast; fun differentiator.
- Later: visibility/fog, snow, UV.
