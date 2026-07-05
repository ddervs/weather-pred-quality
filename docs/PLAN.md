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

## Current state (as of 2026-07-05)

- **Normalisation + metrics engine DONE** (this was the 2026-07-05 chunk):
  - `wpq/normalize.py` → `data/norm/forecasts.parquet` (9.0 M rows) +
    `observations.parquet` (2.9 M rows). Controlled vocab `temp_c, precip_mm,
    wind_ms, gust_ms, rain_occurred`; all unit conversions live there (module
    docstring documents every convention). Full rebuild ≈ 35 s locally.
  - `wpq/metrics.py` + `scripts/run_metrics.py` → `data/metrics/metrics.parquet`:
    sufficient statistics + derived metrics at (model, truth_source, variable,
    lead_day, station, month) grain. Baselines included as pseudo-models
    `persistence`, `climatology_dayofyear` (in-sample, crude — flagged).
    `scores` lib skipped (xarray bloat); metrics hand-rolled in polars.
  - `scripts/report_metrics.py` prints headline tables; findings in
    docs/07-first-real-metrics.md. Acceptance PASSED: temp MAE by lead vs ERA5 =
    0.70/0.84/1.03/1.15/1.36/1.63 °C — identical to the smoke test.
    Notable finding: UKMO 10 m wind loses to day-of-year climatology at leads 4–5.
  - `.github/workflows/metrics.yml`: weekly (Sun 03:40 UTC) + manual; rebuilds
    norm + metrics, commits with the same rebase pattern as collect.yml.
    DEVIATION from the original chunk spec: `data/norm/` is gitignored, only
    `data/metrics/` is committed — forecasts.parquet is 45 MB and rewrites fully
    each run (≈2.3 GB/yr of git bloat) while being a 35 s deterministic rebuild
    from committed inputs. Anything needing data/norm runs
    `uv run scripts/run_metrics.py --normalize` first.
- Deps now: requests, polars(+rtcompat), duckdb (duckdb still unused — drop it
  later if it stays unused). Local gotcha: Danial's local Python runs under
  Rosetta → plain polars crashes; `polars[rtcompat]` fixes it (already in
  pyproject). CI (linux x86) unaffected.
- `land_obs` wind units RESOLVED: m/s (empirically matched co-located METAR
  kt→m/s at 8 airports, 2026-07-05).

## Previous state (2026-07-04 evening)

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
- Previous-runs leads ≥1 d return nulls for 25–45 % of hours (lead 0 is complete), and
  the missing subset differs per lead — cross-lead metric comparisons carry a
  sample-composition caveat (see docs/07). Not a bug; the API just has holes.

## NEXT CHUNK: calibration layer

Goal: quantify *trustworthiness*, not just accuracy. Reliability diagrams +
calibration error with bootstrap CIs; conformal intervals on temperature.

1. Reliability data for rain occurrence: currently the forecast is {0,1} so a
   reliability diagram is two bins — still compute forecast-frequency vs observed-
   frequency + Brier decomposition (reliability/resolution/uncertainty) as scaffolding.
   Real curves arrive with MOGREPS member-fraction PoP (needs ~4 weeks of ensemble
   collection; started 2026-07-04, so ready ~2026-08-01 — check
   `data/raw/ukmo_ensemble/` day count before building).
2. Conformal intervals on temp via MAPIE (Mondrian: region × lead) or hand-rolled
   split-conformal on the backfill (2024 fit / 2025-26 score to dodge the in-sample
   trap). Output: interval half-widths + empirical coverage per lead × region table.
3. Bootstrap CIs on headline metrics (station-level block bootstrap — hours within a
   station-day are correlated; naive iid bootstrap will be overconfident).
4. Extend metrics.parquet or add calibration.parquet; wire into report + docs/08.

## Later chunks (in order, one per session-ish)

1. **Dashboard v1**: static page from metrics.parquet (station map pattern already in
   `scripts/templates/`); per-station scorecards, lead curves, reliability diagrams.
   Host privately first (artifact / local); public Pages + personal site later.
   The wind-loses-to-climatology-at-day-4+ finding deserves a panel.
2. **SEPA/NRW gauges** for Scotland/Wales rain truth; re-pair those stations.
3. **v1.5 data**: Met Office DataHub site-specific product into collector ("model vs
   app product"); widen Open-Meteo model list (ECMWF/ICON/GFS…) — schema already copes.
4. **Ops**: monthly station health report from collected data; repo-size watch
  (`data/raw` grows ~1 MB/day; consider parquet-consolidation + raw pruning at ~1 GB).
  Proper out-of-sample climatology baseline (1991-2020 normals or held-out split).

## Conventions

- Zero cost, ToS-polite, `.env` never committed, key never printed/logged.
- Always `git pull --rebase` before pushing (the collector bot commits to main).
- Commit messages end with the Claude Co-Authored-By line.
- Data decisions that surprised us get recorded in this file or docs/01.
