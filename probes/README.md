# API probes (research phase, 2026-07-03)

Throwaway scripts that verify what the keyless, free APIs actually return for UK
locations. No API keys, no money, single gentle requests. Sample responses are
committed under `samples/` so the shapes can be inspected without re-fetching.

Run any of them with `uv run probes/probe_<name>.py` (from the repo root, after `uv sync`).

| Script | API | Result |
|---|---|---|
| `probe_open_meteo_forecast.py` | Open-Meteo forecast (multi-model) | 10 UK locations × 7 models × 11 hourly vars × 8 days in **one call**: 810 KB raw / 129 KB gz (~81 KB/location raw). All models return UK data. `precipitation_probability` is missing for `ukmo_seamless` and `meteofrance_seamless`. |
| `probe_open_meteo_previous_runs.py` | Open-Meteo Previous Runs | Confirms per-lead-time archived forecasts (`*_previous_day0..7`) work for UK points, archived back to ~Jan 2024 for most models. Models disagreed by up to ~5 °C at day-5 lead for the same valid hour. This makes verification back-fillable without our own cache. |
| `probe_open_meteo_ensemble.py` | Open-Meteo Ensemble | Raw ensemble members per point: MOGREPS-G 18, ECMWF ENS 51, ICON-EU-EPS 40 (GEFS key naming needs a second look — count showed 0, likely a suffix-parsing quirk in the probe, not missing data). ~295 KB raw / 45 KB gz for 1 location, 3 vars, 5 days. |
| `probe_metno.py` | MET Norway locationforecast 2.0 `complete` | 59 KB raw / 4.2 KB gz per location, ~9-day horizon. Sends `Expires` (~30 min) and `Last-Modified` headers which the ToS requires us to honour. **No probabilistic fields for UK points** (percentiles are Nordic-only). |
| `probe_metar.py` | aviationweather.gov METAR | Keyless NOAA endpoint. 10 UK airports, 2 obs/hour each, JSON. Good for temp/wind/pressure ground truth. Caveats: temperatures are integer °C, and UK METARs carry no precipitation amounts (only present-weather codes like `RA`). |
| `probe_metoffice_landobs.py` | Met Office DataHub Land Observations (needs `MET_OFFICE_LAND_OBS_API_KEY` in `.env`) | Probed 2026-07-04 with a real key. `GET /observation-land/1/nearest?lat=&lon=` (coords must be ≤2 dp or HTTP 400) finds the nearest station; `GET /observation-land/1/{geohash}` returns **48 h of hourly obs**: temperature (0.01 °C), humidity, wind speed/gust/direction, visibility, mslp, pressure tendency, weather code. **No rainfall amounts** — occurrence only via `weather_code`. Central London's nearest station (`gcpvj0`) is a dud (timestamps, no values) — station health-checking is required. ~1.7 KB/station/call. |
| `probe_ea_rainfall.py` | Environment Agency flood-monitoring API | Keyless, Open Government Licence. 15-min tipping-bucket rainfall in mm; 14 gauges within 15 km of central London; live readings confirmed. **This is the rain-amounts ground truth for England** (Met Office Land Obs has none). SEPA/NRW cover Scotland/Wales. Individual gauges can be dormant — pick gauges with recent data. |

Key sizing takeaway: a 50-location × 7-model × 4-fetches/day collector produces roughly
**4 MB/day of raw JSON (~650 KB gzipped)** from Open-Meteo plus ~1 MB/day from met.no —
about **1.5 GB/year raw, ~250 MB/year gzipped**. Well within free tiers of everything.

Findings are written up properly in the research archive
([`../docs/research/`](../docs/research/README.md)); the sources that made the cut are
described in [`../docs/data-sources.md`](../docs/data-sources.md).
