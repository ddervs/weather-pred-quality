# Data layout: what is cached on disk, in what format, and what every field means

*Living doc. Last updated 2026-07-05. The unit/vocabulary section mirrors the
`wpq/normalize.py` module docstring — if they disagree, the code docstring wins.*

```
data/
├── stations.json               # the fixed station registry (committed)
├── raw/                        # live collector output, immutable (committed)
│   ├── ukmo_forecast/YYYY-MM-DD/HHMMZ.json.gz
│   ├── ukmo_ensemble/YYYY-MM-DD/HHMMZ.json.gz      # 00Z/12Z runs only
│   ├── land_obs/YYYY-MM-DD/HHMMZ.json.gz
│   ├── ea_rain/YYYY-MM-DD/HHMMZ.json.gz
│   ├── sepa_rain/YYYY-MM-DD/HHMMZ.json.gz           # since 2026-07-05
│   ├── nrw_rain/YYYY-MM-DD/HHMMZ.json.gz            # since 2026-07-05
│   └── metar/YYYY-MM-DD/HHMMZ.json.gz
├── backfill/                   # one-off historical pull, immutable (committed)
│   ├── prev_runs/{start}_{end}_c{ci}.json.gz       # UKMO forecasts, leads 0–5 d
│   └── era5/{start}_{end}_c{ci}.json.gz            # ERA5 truth
├── norm/                       # tidy Parquet — GITIGNORED, deterministic ~35 s rebuild
│   ├── forecasts.parquet       #   (uv run scripts/run_metrics.py --normalize)
│   └── observations.parquet
├── metrics/                    # final outputs (committed, rebuilt weekly by CI)
│   ├── metrics.parquet
│   ├── conformal.parquet
│   ├── brier_decomposition.parquet
│   └── bootstrap_ci.parquet
└── geo/coast.json              # UK coastline for the station map
```

Design rule: **raw and backfill are the immutable audit trail; everything else is a
deterministic rebuild from them.** Late, duplicate, or re-run collections are harmless —
payloads carry their own timestamps and normalisation dedupes (keep-last).

---

## `data/stations.json` — the station registry

Built once by `scripts/build_station_registry.py` (2026-07-04). **Do not move stations
casually** — continuity matters. Top level: `built_at`, `notes`, `stations` (list of 33):

```jsonc
{
  "id": "gcqf99",          // Met Office station geohash = station ID everywhere
  "seed_city": "Birmingham", // which seed city found this station
  "lat": 52.4789, "lon": -1.6864,  // decoded geohash centre (the station, not the city)
  "area": "Warwickshire",  // Met Office metadata
  "region": "wm",          // Met Office region code (se, sw, yh, nw, wm, gr, …)
  "country": "England",    // one of the four UK nations — main segmentation key
  "ea_gauge": {            // nearest live EA rain gauge, or null (all non-England, 9 stations)
    "station_reference": "3340",
    "measure": "3340-rainfall-tipping_bucket_raingauge-t-15_min-mm",
                           // pinned rainfall TOTALS measure — some gauges publish extra
                           // intensity/duplicate series; the collector fetches ONLY this
    "period": 900,         // seconds per reading: 900, or 3600 for the two hourly-only
                           // gauges (Cambridge E5731, Lincoln E5721)
    "lat": 52.446, "lon": -1.746, "distance_km": 5.5
  },
  "metar": { "icao": "EGBB", "distance_km": 5.0 },  // nearest airport ≤40 km, or null (8 stations)
  "sepa_gauge": {          // nearest live SEPA rain gauge — Scotland only, null elsewhere
    "station_no": "15196", "name": "Gogarbank",
    "ts_id": "56594010",   // KiWIS 15-min Precip series ID, pre-resolved so the
                           // collector fetches all gauges in ONE getTimeseriesValues call
    "lat": 55.928211, "lon": -3.343123, "distance_km": 0.2
  },
  "nrw_gauge": {           // nearest live NRW rain gauge — Wales only, null elsewhere
    "station_id": 1027, "name": "Llyn Cefni",
    "parameter": 10122,    // NRW Rainfall parameter IDs are PER-STATION — stored so
                           // the collector can query without a lookup
    "lat": 53.286865, "lon": -4.36358, "distance_km": 3.2
  }
}
```

## `data/raw/` — live collector payloads

One gzipped JSON file per source per collector run (every 6 h; filename = fetch time
UTC). Shapes, and the gotchas that cost real time to learn:

- **`ukmo_forecast/`** — Open-Meteo response: a *list* of per-location objects, **ordered
  exactly as `stations.json`** — there is no station ID in the response, join by
  position. Each has `hourly.time[]` plus arrays for the 9 requested variables (native
  units: °C, mm, km/h, degrees, %, okta-ish cloud %). The model **init time is not in
  the payload**; lead is approximated as `valid_time − fetch_time`.
- **`ukmo_ensemble/`** — same list-ordered shape; hourly keys look like
  `temperature_2m_member03_ukmo_global_ensemble_20km` (no `_memberNN` = member 0 =
  control run).
- **`land_obs/`** — `{geohash: [up to 48 hourly entries] | null}`. Entry fields:
  `datetime`, `temperature` (**hundredths of °C**), `humidity` (%), `wind_speed` /
  `wind_gust` (**m/s** — verified empirically against co-located METAR kt→m/s at 8
  airports, 2026-07-05), `wind_direction` (compass string), `visibility` (m), `mslp`
  (hPa), `pressure_tendency`, `weather_code` (int — rain occurrence comes from this).
  **No rain amounts.** Dud stations return timestamp-only entries.
- **`ea_rain/`** — `{station_reference: {items: [{dateTime, value, measure, …}]}}`;
  `value` = mm total for the interval ending at `dateTime`. Gauges go dormant; values
  are occasionally negative or absurd — QC happens at normalisation (clamp `< 0` to 0,
  discard `> 20 mm/15 min`, `> 80 mm/h` for hourly gauges). **Measure gotchas (found
  2026-07-06 when the weekly report flagged silent gauges)**: two gauges (Cambridge
  `E5731`, Lincoln `E5721`) publish **hourly** totals only (`…-t-1_h-mm`) — the
  4-slice hour rule silently discarded everything they sent; six others publish a
  second rainfall series (`…-i-15_min` intensity or `rainfall-water`) that doubled the
  row rate and truncated the 30 h window (`_limit=120`) — and at four of those
  (Brighton, Dover, Newcastle, Sheffield) the *totals* series is **dormant** and the
  twin is the live one (`i` vs `t` values agree to ~5% on a rainy Leeds sample —
  per-stamp tip-attribution jitter, sums match). Since 2026-07-06 the collector
  fetches one pinned measure per gauge (`ea_gauge.measure`, chosen by reading
  freshness, not name — `fetch_ea_rain_measure`); the loader also filters older
  whole-station payloads by that measure, so history was recovered retroactively.
- **`sepa_rain/`** — SEPA KiWIS response: a *list* of series objects, one per gauge,
  each `{station_no, station_name, ts_id, ts_unitsymbol, rows, columns, data}` where
  `data` = `[["2026-07-05T17:45:00.000Z", 0.2], …]` — mm per 15-min interval, timestamp
  = interval **end** (same convention as EA; SEPA's `Day.Total` series stamping at
  09:00, the end of the hydrological day, confirms end-labelling). The response carries
  `ts_id`, not our geohash — join back through `sepa_gauge.ts_id` in `stations.json`.
  Values ~30 min behind real time. Same dormancy/QC caveats as EA; the dead
  `apps.sepa.org.uk` API is *not* this one (`timeseries.sepa.org.uk` is current).
- **`nrw_rain/`** — `{station_id: {…, units, parameterReadings: [{time, value}]}}`;
  `value` = mm per 15-min interval, `time` = interval end (as EA/SEPA). Fetched one
  call per gauge with a `from`/`to` date window — **the historical endpoint returns a
  full year (~1.5 MB) if unwindowed**, and `from`/`to` are the only window params it
  honours. Needs `NRW_API_KEY`. `statusEN: "Online"` is unreliable (gauges dead since
  2023 still say it) — liveness = the Rainfall parameter's `latestTime`. Rainfall
  `parameter` IDs differ per station (from `/StationData`'s `parameters[]`).
- **`metar/`** — list of observations across all airports; `temp` **integer** °C, `wspd`
  knots, `wxString` present-weather codes (`RA`, `DZ`, …), ~2 obs/hour. No rain amounts.

## `data/backfill/` — the 2024→2026 historical pull

One-off from `scripts/backfill_ukmo.py` (13.8 MB total). Files are chunked
`{start}_{end}_c{ci}.json.gz` by quarter and by station chunk: `CHUNK_SIZE = 11`, so
chunk `ci` covers `stations[ci*11:(ci+1)*11]` — again, **responses are position-ordered
lists; the chunk index is the only key back to station IDs**.

- **`prev_runs/`** — Previous Runs API: hourly arrays named
  `{variable}_previous_day{N}` for leads 1–5 (value = what was forecast ~N×24 h before
  the valid hour) — **except lead 0, which arrives under the plain variable name**
  (`temperature_2m`; there is no `_previous_day0` key). Leads ≥ 1 have 25–45 % null
  hours, differing per lead (API holes, not a bug).
- **`era5/`** — Open-Meteo archive API (ERA5 reanalysis), same hourly-array shape,
  used as truth for the backfill period.

## `data/norm/` — the tidy tables (gitignored)

Everything above is parsed into two long Parquet tables by `wpq/normalize.py`; **all unit
conversion happens there and only there**. Full rebuild each run (idempotent):
`uv run scripts/run_metrics.py --normalize`.

**`forecasts.parquet`** (~9 M rows):

| column | meaning |
|---|---|
| `source` | `prev_runs` \| `ukmo_forecast` \| `ukmo_ensemble` |
| `model` | `ukmo_seamless` \| `ukmo_global_ensemble_20km` |
| `station_id` | geohash from `stations.json` |
| `init_time` | UTC. `prev_runs`: `valid_time − lead` (approx, daily granularity); live sources: collector fetch time |
| `valid_time` | UTC, hourly — the hour the forecast is *about* |
| `lead_hours` | int; live rows with negative lead (past hours in the payload) are dropped |
| `variable` | controlled vocabulary, below |
| `value` | float, normalised units |
| `member` | ensemble member (0 = control); null for deterministic |

**`observations.parquet`** (~3 M rows): `source` (`era5` \| `land_obs` \| `ea_rain` \|
`sepa_rain` \| `nrw_rain` \| `metar`), `station_id`, `valid_time`, `variable`, `value`.

### The controlled variable vocabulary (and every unit convention)

| variable | unit | conversions & conventions |
|---|---|---|
| `temp_c` | °C | Open-Meteo/ERA5 native; land_obs ÷ 100 (0.01 °C resolution); METAR integer °C |
| `precip_mm` | mm accumulated over the hour **preceding** `valid_time` (Open-Meteo convention) | EA/SEPA/NRW 15-min readings (all mm totals for the 15 min ending at their timestamp) summed into that window — an hour needs all four slices to count. QC: negatives clamped to 0, single readings > 20 mm/15 min discarded |
| `wind_ms` | m/s | Open-Meteo/ERA5 km/h ÷ 3.6; METAR knots × 0.514444; land_obs already m/s |
| `gust_ms` | m/s | same conversions as `wind_ms` |
| `rain_occurred` | 0/1 — "did it rain this hour?" | era5 and the rain gauges (ea/sepa/nrw): hourly `precip_mm ≥ 0.1`. land_obs: Met Office significant-weather code in the liquid-precip set {9–18, 28–30} (rain/drizzle/sleet/thunder; hail and snow excluded). metar: `wxString` contains `RA` or `DZ` — instantaneous at obs time, read as "raining around the top of the hour" |

METAR reports ~2/h; the report nearest each top-of-hour (±30 min) is kept. Overlapping
48 h land-obs windows across collections are deduped keep-last (later file wins).

## `data/metrics/` — the outputs (committed)

- **`metrics.parquet`** (from `wpq/metrics.py`) — one row per
  `(model, truth_source, variable, lead_days, station_id, month)` cell, where `model`
  includes the pseudo-models `persistence` and `climatology_dayofyear` (baselines).
  Columns are **sufficient statistics** (`n`, `sum_err`, `sum_abs_err`, `sum_sq_err`,
  `sum_brier`, `hits`, `misses`, `false_alarms`, `correct_negatives`, …) plus derived
  convenience metrics (`mae`, `rmse`, `bias`, `brier`, `pod`, `far`, `csi`, `ets`,
  `base_rate`). **Rule: any coarser segmentation (nation, season, UK-wide) must
  re-aggregate the sums — never average the derived MAEs/ETSs.**
- **`conformal.parquet`** (from `wpq/calibration.py`) — per `(country, lead_days)`:
  `alpha` (0.1), `n_cal`, `q_hat` (the ± half-width in °C), `n_test`, `coverage`
  (achieved on the 2025–26 test period; target 0.90).
- **`brier_decomposition.parquet`** — per `lead_days`: `brier` = `reliability` −
  `resolution` + `uncertainty`, plus `brier_skill` vs base rate.
- **`bootstrap_ci.parquet`** — per `(metric, lead_days)`: `estimate`, `ci_lo`, `ci_hi`
  (95 %, station-day block bootstrap, B = 1000, fixed seed), `n_blocks`.

What the metrics *mean* and how they're computed: [methodology.md](methodology.md).
