# Working plan — "carry on with the plan" starts here

Written 2026-07-04. This is the session-to-session handoff doc. When Danial says
"carry on with the plan", read this file top to bottom, check **Current state** against
reality (`git log`, `ls data/`), then start the **Next chunk**.

## Project in one paragraph

Verify UK weather forecasts against observations; publish reliability scores segmented by
region / lead time / variable. v1 scope: **UKMO model forecasts only** (via Open-Meteo),
ground truth = Met Office land obs + EA rain gauges + METAR. Strictly £0. No BBC. North
star (docs/00-overview.md): calibrated probabilistic UK map, conformal guarantees.
Research: docs/00..05. Repo is private for now; **eventual dashboard hosting = public
GitHub Pages on Danial's personal site, like github.com/ddervs/restaurant-review-map —
but only after everything works privately** (his explicit preference, 2026-07-04).

## Current state (as of 2026-07-04 evening)

- `data/stations.json` — 33 fixed stations (Met Office geohash + EA gauge + METAR
  triples). Locations = decoded geohash centres. Do not move stations casually.
- Collector live: `.github/workflows/collect.yml` runs `wpq.collect` every 6 h
  (ensembles only on 00Z/12Z runs), commits gzipped JSON to `data/raw/{source}/{date}/{HHMM}Z.json.gz`.
  Sources: `ukmo_forecast`, `ukmo_ensemble`, `land_obs`, `ea_rain`, `metar`.
  Secret `MET_OFFICE_LAND_OBS_API_KEY` is set in the repo (also in local `.env`).
- Backfill DONE (`scripts/backfill_ukmo.py`): `data/backfill/prev_runs/` (UKMO leads
  0–5 d, 2024-01-01..2026-06-30, 30 files) + `data/backfill/era5/` (truth, 15 files),
  chunked `{start}_{end}_c{ci}.json.gz`, 13.8 MB total. Smoke test PASSED — pipeline
  verified, results + gotchas in docs/06-smoke-test.md (temp MAE 0.70→1.63 °C over
  leads 0→5). Keep "error grows with lead" as a permanent regression check.
- Station map: `docs/station-map.html/.png`, regenerate via
  `uv run scripts/make_station_map.py --screenshot` when the registry changes.

## Data format gotchas (cost real time to learn — trust these)

- **Open-Meteo multi-location responses are ordered lists matching request order**,
  which is `stations.json` order (or chunks of it: backfill uses `CHUNK_SIZE = 11`,
  chunk `ci` = `stations[ci*11:(ci+1)*11]`). No station id in the response — join by position.
- Open-Meteo previous-runs: `var_previous_dayN` = value predicted ~N×24 h before valid
  time. Only deterministic runs; lead granularity is daily. **Lead 0 comes back under the
  plain variable name** (`temperature_2m`), not `_previous_day0` (that key is absent).
- Live `ukmo_forecast` files: init/issue time is NOT in the payload; approximate lead as
  `valid_time − fetch_time` (fetch time = filename). Good enough at 6 h cadence; note it.
- `land_obs` files: `{geohash: [48 hourly entries] | null}`; entries have `datetime`,
  `temperature` (0.01 °C), `humidity`, `wind_speed`/`wind_gust` (units TBC — check! knots
  vs m/s vs mph not yet verified), `wind_direction` (compass str), `visibility` (m),
  `mslp`, `pressure_tendency`, `weather_code` (int; rain occurrence from code table).
  **No rain amounts.** Dud stations return timestamp-only entries.
- `ea_rain` files: `{station_reference: {items: [{dateTime, value(mm/15min), …}]}}`;
  gauges can go dormant; values occasionally negative/absurd (QC needed: clamp `<0`,
  flag `>20 mm/15min`).
- `metar` files: list of obs; `temp` integer °C, `wspd` knots, no rain amounts,
  `wxString` codes; 2 obs/h.
- Met Office `nearest` endpoint needs ≤2 dp coords; obs API is per-station geohash.

## NEXT CHUNK: normalisation layer + real metrics engine

Goal: from raw/backfill files to one queryable table, then first real skill numbers.
Acceptance: a `metrics.parquet` whose MAE-by-lead broadly reproduces the smoke test, plus
Brier/reliability for rain occurrence and CRPS (deterministic ⇒ CRPS = MAE), segmented.

1. **Deps**: `uv add duckdb polars scores` (scores is the BoM verification lib; if it
   drags in heavy xarray deps and annoys, fall back to hand-rolled + properscoring).
2. **`wpq/normalize.py`** → writes Parquet under `data/norm/`:
   - `forecasts.parquet`: `(source, model, station_id, init_time, valid_time,
     lead_hours, variable, value, member)` — member NULL for deterministic.
     Readers: backfill prev_runs (lead from `_previous_dayN`), raw ukmo_forecast
     (lead from fetch ts), raw ukmo_ensemble (member from key suffix).
   - `observations.parquet`: `(source, station_id, valid_time, variable, value)` —
     readers: land_obs, ea_rain (aggregate 15-min → hourly mm), metar, backfill era5
     (source='era5' so model-truth vs obs-truth can be compared).
   - Normalise variables to a small controlled vocabulary: `temp_c`, `precip_mm`,
     `wind_ms`, `gust_ms`, `rain_occurred` (derived: EA mm>=0.1 | weather_code rain set).
     Units converted at this layer, documented in the module docstring.
   - Idempotent: full rebuild from files each run is fine at current volumes (<10 min);
     partition by month if slow.
3. **`wpq/metrics.py` + `scripts/run_metrics.py`** → `data/metrics/metrics.parquet`:
   - Joins forecasts×observations on (station, valid hour, variable).
   - Metrics per segment `(truth_source, variable, lead_day, region, country, season, month)`:
     MAE, bias, RMSE, n; rain: Brier (occurrence as {0,1} forecast for now), POD/FAR/CSI/ETS.
   - Baselines in same table as pseudo-models: `persistence` (obs 24 h earlier),
     `climatology_dayofyear` (mean over the 2.5 y ERA5 sample per station×doy×hour —
     crude, flag it; proper 1991-2020 climatology is a later upgrade).
   - Skill scores computed at query/report time, not stored.
4. **Report**: `scripts/report_metrics.py` printing the headline table (MAE by lead ×
   nation; ETS by lead) + write `docs/07-first-real-metrics.md` with findings.
5. **CI**: extend Actions with a weekly `metrics.yml` (workflow_dispatch + cron Sun
   03:40 UTC): run normalize + metrics, commit `data/norm` + `data/metrics`.
   Mind the race with the 6-hourly collect workflow: `git pull --rebase` before push
   (already the pattern in collect.yml).

## Later chunks (in order, one per session-ish)

1. **Calibration layer**: reliability diagrams + calibration error w/ bootstrap CIs
   (`uncertainty-calibration`), PoP from ensemble member fraction once ~4 weeks of
   MOGREPS accumulate; conformal intervals via MAPIE (Mondrian: region × lead) on temp.
2. **Dashboard v1**: static page from metrics.parquet (station map pattern already in
   `scripts/templates/`); per-station scorecards, lead curves, reliability diagrams.
   Host privately first (artifact / local); public Pages + personal site later.
3. **SEPA/NRW gauges** for Scotland/Wales rain truth; re-pair those stations.
4. **v1.5 data**: Met Office DataHub site-specific product into collector ("model vs
   app product"); widen Open-Meteo model list (ECMWF/ICON/GFS…) — schema already copes.
5. **Ops**: monthly station health report from collected data; repo-size watch
  (`data/raw` grows ~1 MB/day; consider parquet-consolidation + raw pruning at ~1 GB).

## Conventions

- Zero cost, ToS-polite, `.env` never committed, key never printed/logged.
- Always `git pull --rebase` before pushing (the collector bot commits to main).
- Commit messages end with the Claude Co-Authored-By line.
- Data decisions that surprised us get recorded in this file or docs/01.
