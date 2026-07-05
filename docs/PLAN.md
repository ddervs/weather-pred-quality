# Working plan — "carry on with the plan" starts here

Written 2026-07-04. This is the session-to-session handoff doc. When Danial says
"carry on with the plan", read this file top to bottom, check **Current state** against
reality (`git log`, `ls data/`), then start the **Next chunk**.

## Project in one paragraph

Verify UK weather forecasts against observations; publish reliability scores segmented by
region / lead time / variable. v1 scope: **UKMO model forecasts only** (via Open-Meteo),
ground truth = Met Office land obs + EA rain gauges + METAR. Strictly £0. No BBC. North
star (docs/research/00-overview.md): calibrated probabilistic UK map, conformal guarantees.
Living guide docs: docs/README.md (overview / data-sources / data-layout / methodology /
glossary); research archive: docs/research/; dated findings: docs/results/.
Repo is private for now; **eventual dashboard hosting = public
GitHub Pages on Danial's personal site, like github.com/ddervs/restaurant-review-map —
but only after everything works privately** (his explicit preference, 2026-07-04).

## Current state (as of 2026-07-05, second chunk)

- **Docs reorganised** (2026-07-05, side task): living guide docs
  (docs/{overview,data-sources,data-layout,methodology,glossary}.md + docs/README.md
  index), dated findings moved to docs/results/, research phase preserved verbatim in
  docs/research/ (old 00–05). The "data format gotchas" list now lives in
  docs/data-layout.md — keep it updated there, not here. New data-shape surprises:
  record in data-layout.md; new source decisions: data-sources.md.
- **Calibration layer DONE** (same day, second chunk):
  - `wpq/calibration.py` + `scripts/run_calibration.py` →
    `data/metrics/{conformal,brier_decomposition,bootstrap_ci}.parquet`; wired
    into metrics.yml (runs after run_metrics). ~15 s locally. numpy added.
  - Split conformal (hand-rolled, no MAPIE), Mondrian nation × lead, |error|
    scores, cal=2024 / test=2025-26: **coverage 0.89–0.93 vs 0.90 target in
    every cell**. UK 90 % half-widths ±1.5 °C (d0) → ±3.6 °C (d5).
  - Murphy decomposition finding: **binary rain forecast has negative Brier
    skill vs base rate from day 2** (resolution collapses, reliability penalty
    balloons) — the killer argument for MOGREPS PoP; same code will draw real
    reliability curves once ~4 wks of ensembles exist (~2026-08-01).
  - Station-day block bootstrap (B=1000): headline CIs ±0.005–0.015 — all
    lead-to-lead differences significant. Findings + caveats in
    docs/results/2026-07-05-calibration.md.
  - All of it is vs ERA5 truth; redo vs live obs once months accumulate.

## Earlier state (2026-07-05, first chunk)

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
    docs/results/2026-07-05-first-real-metrics.md. Acceptance PASSED: temp MAE by lead vs ERA5 =
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
  verified, results + gotchas in docs/results/2026-07-04-smoke-test.md (temp MAE 0.70→1.63 °C over
  leads 0→5). Keep "error grows with lead" as a permanent regression check.
- Station map: `docs/station-map.html/.png`, regenerate via
  `uv run scripts/make_station_map.py --screenshot` when the registry changes.

## Data format gotchas (cost real time to learn — trust these)

**Moved to docs/data-layout.md** (2026-07-05 docs reorg) — the full list of payload
shapes, unit conventions and API quirks lives there now; record new surprises there.
One item that stays here because it's an API-call constraint, not a data-shape fact:

- Met Office `nearest` endpoint needs ≤2 dp coords; obs API is per-station geohash.

## NEXT CHUNK: dashboard v1 (private)

Goal: the numbers exist; make them legible. Static, self-contained HTML from the
committed `data/metrics/*.parquet` — no server, £0. Private first (open locally /
artifact); public Pages + personal site only when Danial says so.

1. `scripts/make_dashboard.py` → `docs/dashboard.html`, following the pattern of
   `scripts/make_station_map.py` + `scripts/templates/` (embed JSON payload +
   inline JS/CSS; no CDN so it works offline and on Pages later).
2. Panels, in priority order:
   - Lead curves: temp MAE + rain ETS by lead with the bootstrap CI bands
     (bootstrap_ci.parquet), UKMO vs persistence vs climatology.
   - **The wind panel**: UKMO wind MAE vs climatology crossing at day ~3.5 —
     the headline finding, deserves its own chart.
   - Conformal: half-width fan (±q̂ by lead) + coverage-vs-target strip, per nation.
   - Brier decomposition stacked bars by lead (shows the negative-skill story).
   - Per-station scorecard table (station, nation, temp MAE d1/d5, ETS d1, n) from
     metrics.parquet sufficient stats — re-aggregate sums, never average MAEs.
3. Screenshot into README like the station map (`--screenshot` flag, same
   playwright pattern as make_station_map.py).
4. Regenerate in metrics.yml after calibration step; commit docs/dashboard.html.
   Keep the payload lean: aggregate in Python, embed only what's plotted (< ~200 kB).

## Later chunks (in order, one per session-ish)

1. **PoP + real reliability curves** (~2026-08-01, once `data/raw/ukmo_ensemble/`
   spans ~4 weeks): member-fraction PoP per lead, multi-bin reliability via the
   existing Brier-decomposition code, add to metrics + dashboard. Also redo the
   headline tables vs live obs truth (land_obs/EA/METAR) as the ERA5 credibility
   check — docs/results/2026-07-05-calibration.md caveat.
2. **SEPA/NRW gauges** for Scotland/Wales rain truth; re-pair those stations.
3. **v1.5 data**: Met Office DataHub site-specific product into collector ("model vs
   app product"); widen Open-Meteo model list (ECMWF/ICON/GFS…) — schema already copes.
4. **Ops**: monthly station health report from collected data; repo-size watch
  (`data/raw` grows ~1 MB/day; consider parquet-consolidation + raw pruning at ~1 GB).
  Proper out-of-sample climatology baseline (1991-2020 normals or held-out split).
  Drop duckdb if still unused. Bump actions/checkout + setup-uv (Node 20 warning).

## Conventions

- Zero cost, ToS-polite, `.env` never committed, key never printed/logged.
- Always `git pull --rebase` before pushing (the collector bot commits to main).
- Commit messages end with the Claude Co-Authored-By line.
- Data decisions that surprised us get recorded in docs/data-layout.md (payload/unit
  surprises), docs/data-sources.md (source decisions), or this file (plan-level).
