# Working plan — "carry on with the plan" starts here

Written 2026-07-04. This is the session-to-session handoff doc. When Danial says
"carry on with the plan", read this file top to bottom, check **Current state** against
reality (`git log`, `ls data/`), then start the **Next chunk**.

## Project in one paragraph

Verify UK weather forecasts against observations; publish reliability scores segmented by
region / lead time / variable. v1 scope: **UKMO model forecasts only** (via Open-Meteo),
ground truth = Met Office land obs + EA/SEPA/NRW rain gauges + METAR. Strictly £0. No BBC. North
star (docs/research/00-overview.md): calibrated probabilistic UK map, conformal guarantees.
Living guide docs: docs/README.md (overview / data-sources / data-layout / methodology /
glossary); research archive: docs/research/; dated findings: docs/results/.
Repo is private for now; **eventual dashboard hosting = public
GitHub Pages on Danial's personal site, like github.com/ddervs/restaurant-review-map —
but only after everything works privately** (his explicit preference, 2026-07-04).

## Current state (as of 2026-07-05, second chunk)

- **Ensemble collection was silently dead — fixed** (2026-07-06, found by the
  source-down alert's very first firing): GitHub cron runs arrive HOURS late
  (00:20 → 04:41 observed), so wpq.collect's `hour in (0,1,12,13)` ensemble
  gate never matched a scheduled run; the only ensemble file ever was from a
  manual dispatch. Now self-scheduled: collect ensembles when the last
  ensemble raw file is ≥10 h old (~2/day). Assume ALL cron times are +2–5 h.
- **Weekly health email wired in** (2026-07-05, side task): `weekly-report.yml`
  (Mondays 03:20 UTC — cron fires +2–5 h late, landing it in the UK morning)
  runs `scripts/make_weekly_report.py` → RAG tables for the
  7 collector sources (run completeness + station coverage) and for model ×
  variable metrics vs a trailing 4-week live-obs baseline (⚪ until ~4 weeks of
  live obs exist, ~2026-08). Delivery = the scotbet pattern: issue created with
  `_cc @ddervs_`, GitHub emails the mention, issue instantly closed (label
  `weekly-report`). Plus a mid-week backstop: collect.yml now runs
  `scripts/check_source_alerts.py` after every run (`if: always()`) and raises a
  `source-alert` issue when a source has been dead 24 h+ (dedup: one per source
  per 7 days). Also fixed: collect.yml's commit step now `if: always()`, so one
  failing source no longer loses the other sources' data. All RAG thresholds
  live at the top of make_weekly_report.py. First report flagged Cambridge +
  Lincoln EA gauges silent → root cause found and fixed 2026-07-06: they are
  hourly-only gauges (and 6 others had duplicate intensity series truncating
  the fetch window). EA measures now pinned per gauge in stations.json
  (`scripts/add_ea_measures.py`); details in docs/data-layout.md.

- **SEPA rain gauges wired in** (2026-07-05, side task — was "later chunk 2"):
  Scotland rain-amount truth now live. SEPA's KiWIS API (`timeseries.sepa.org.uk`,
  keyless, OGL, attribute SEPA) → new collector source `sepa_rain` (ONE batched
  getTimeseriesValues call for all gauges) → `load_sepa_rain` in normalize.py
  (shares EA's hour-bucketing/QC via new `gauge_hours`/`qc_15min` helpers) →
  flows through metrics automatically (`truth_source='sepa_rain'`). All 6 Scottish
  stations paired via `scripts/add_sepa_gauges.py` (stations.json now carries
  `sepa_gauge` with pre-resolved `ts_id`; registry builder updated for future
  rebuilds). Verified end-to-end: 6 stations × ~29 h of precip_mm flowing, pairs
  in metrics.parquet. NI: no free gauge API found.
- **NRW rain gauges wired in** (2026-07-05, same day — Danial signed up and put
  `NRW_API_KEY` in `.env`; secret pushed to Actions via `gh secret set`, collect.yml
  passes it): new collector source `nrw_rain`, one windowed call per Welsh gauge
  (`from`/`to` dates are the ONLY window params the historical endpoint honours —
  unwindowed = a full year, 1.5 MB). Bangor→Llyn Cefni (3.2 km), Cardiff→Llantwit
  Major (4.5 km; Cardiff's old EA gauge — 22.6 km away in Somerset — kept for
  continuity but nrw_rain is the credible truth there). `load_nrw_rain` shares the
  gauge helpers; verified end-to-end into metrics.parquet. Gotchas: NRW `statusEN`
  lies (liveness = parameter `latestTime`), Rainfall parameter IDs are per-station.
  **Rain-amount truth now covers 31/33 stations** (all but the 2 NI ones).
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
  (ensembles ~2/day, self-scheduled since 2026-07-06 — the original 00Z/12Z
  hour gate never fired because GitHub cron runs arrive hours late), commits
  gzipped JSON to `data/raw/{source}/{date}/{HHMM}Z.json.gz`.
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

## DONE 2026-07-06: dashboard v1 (private)

`scripts/make_dashboard.py` + `scripts/templates/dashboard.html` →
`docs/dashboard.html` (self-contained, no CDN, dark-mode; regenerated weekly in
metrics.yml; README screenshot). Selectable station map (day-1 temp MAE bins) +
nation/station scope chips re-cut every panel; temp/rain/wind lead curves vs
persistence + climatology; conformal card; Brier-skill card; scorecard table;
plain-language definitions block; data-table twin under every chart. Reviewed by
Danial 2026-07-06. Notes: CI bands auto-hide when narrower than the line (current
bootstrap CIs are sub-pixel); **rain buckets** added same day — `rain_ge_{0.5,1,2,4}`
variables in wpq/metrics.py (model + persistence + climatology, amount-reporting
truth sources only) with a "Rain event" chip group in the dashboard ("Any" = 0.1).
Finding: ETS collapses with severity (day-0: 0.34 any → 0.08 at ≥4 mm/h; ~0 by day 4-5).

## NEXT CHUNK: live-forecast reliability page (Danial's ask 2026-07-06 — big, staged)

Goal: not just scoring the past — for each station, pull the CURRENT UKMO forecast
in the browser and translate it into calibrated event statements backed by our
verification history: "forecast says 2.3 mm at 15:00 tomorrow → when it said that
in 2024-26, ≥1 mm actually fell 64 % of the time; 90 % of temps landed within
±1.7 °C of the number shown". Static page, no server: api.open-meteo.com sends
CORS `*`, so the page can fetch live client-side (attribution required, £0).

Stages (one session each-ish):
1. **Conditional reliability tables** from the backfill: P(obs event | forecast
   bucket, lead, nation-or-station) for the rain buckets, plus temp interval
   half-widths from conformal.parquet. Precompute in Python → compact JSON
   (mind payload size; nation-level first, station-level only if it stays lean).
   Watch small-n cells (heavy rain × long lead × station is sparse — back off
   to nation or wider bucket, and say so in the UI).
2. **The page**: per-station "next 5 days" strip — live Open-Meteo fetch
   (`ukmo_seamless`, same params as the collector), apply the lookup tables,
   render event probabilities + intervals. Graceful degradation: no network →
   history-only view. Extend dashboard or sibling page (`docs/live.html`);
   reuse the map + scope chrome.
3. **Calibrated PoP upgrade** (once ensembles span ~4 wks, from 2026-07-06):
   member-fraction PoP corrected by an isotonic/reliability-curve fit against
   the accumulating live-obs record; replaces the binary-conditioned tables.
Caveats: conditional tables are ERA5-truth until live obs mature (label it);
verify Open-Meteo ToS attribution line on the page before any public hosting.

## Later chunks (in order, one per session-ish)

1. **PoP + real reliability curves** (~2026-08-01, once `data/raw/ukmo_ensemble/`
   spans ~4 weeks): member-fraction PoP per lead, multi-bin reliability via the
   existing Brier-decomposition code, add to metrics + dashboard. Also redo the
   headline tables vs live obs truth (land_obs/EA/METAR) as the ERA5 credibility
   check — docs/results/2026-07-05-calibration.md caveat.
2. ~~SEPA/NRW gauges~~ DONE 2026-07-05 (both). GB rain-amount truth complete;
   only the 2 NI stations lack it (no free gauge API).
3. **v1.5 data**: Met Office DataHub site-specific product into collector ("model vs
   app product"); widen Open-Meteo model list (ECMWF/ICON/GFS…) — schema already copes.
4. **Ops**: ~~station health report~~ DONE 2026-07-05 (weekly RAG email,
  weekly-report.yml). Still to do: repo-size watch
  (`data/raw` grows ~1 MB/day; consider parquet-consolidation + raw pruning at ~1 GB).
  Proper out-of-sample climatology baseline (1991-2020 normals or held-out split).
  Drop duckdb if still unused. Bump actions/checkout + setup-uv (Node 20 warning).

## Conventions

- Zero cost, ToS-polite, `.env` never committed, keys (Met Office, NRW) never
  printed/logged.
- Always `git pull --rebase` before pushing (the collector bot commits to main).
- Commit messages end with the Claude Co-Authored-By line.
- Data decisions that surprised us get recorded in docs/data-layout.md (payload/unit
  surprises), docs/data-sources.md (source decisions), or this file (plan-level).
