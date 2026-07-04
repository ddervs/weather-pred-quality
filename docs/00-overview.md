# UK forecast verification — research summary & options (2026-07-03)

**North star**: a UK map serving calibrated probabilistic weather forecasts blended from
multiple sources, with reliability guaranteed by conformal-style methods.
**Tonight's question**: which data sources, how to cache and evaluate forecasts against
reality, what exists already, what it costs.

## TL;DR findings

1. **The data problem is ~80 % solved by Open-Meteo** (free, keyless, non-commercial):
   it exposes UKMO/ECMWF/ICON/GFS/Météo-France/met.no models individually per UK point,
   plus **raw ensemble members** (MOGREPS, ECMWF ENS — 100+ members/point), plus a
   **Previous Runs API archiving lead-time-stratified forecasts back to ~Jan 2024**.
   That last one means ~2.5 years of verification data is available *today, before we've
   cached anything* — probe-verified (`probes/`).
2. **What still needs live caching from day 1** (no upstream archive): Open-Meteo
   *ensembles*, met.no consumer forecasts, and Met Office DataHub site forecasts
   (free tier: 360 calls/day — enough for ~50 sites).
3. **Ground truth**: Met Office Land Observations API (free 360/day, ~150 stations,
   probed 2026-07-04: temp/wind/humidity/visibility/pressure but **no rain amounts on the
   free tier**) + Environment Agency rain gauges (keyless, OGL, 15-min amounts in mm,
   probed) + NOAA METAR as cross-check. Pick our ~50 locations *at observation stations*.
4. **Nobody occupies this niche openly.** ForecastAdvisor/ForecastWatch are closed and
   US-centric; the University of Reading runs exactly this comparison but at n=1 location
   (Reading), 2 providers, no code/data published. All the metric machinery exists as
   maintained OSS (`scores`, WFRT `verif`, `uncertainty-calibration` — the actual
   Kumar–Liang–Ma code — and MAPIE for conformal). The novel part is the assembly + the
   calibration layer + an open UK map.
5. **BBC Weather has no official API** (DTN-powered); scraping is ToS-grey. Default: skip
   BBC initially, represent "consumer apps" via met.no/Yr + Met Office + optionally
   OpenWeatherMap. Decision yours (doc 01).
6. **£0/month covers phases 1–2 entirely** with ~10× quota headroom; the first money worth
   spending later is £9/mo for the Met Office's own calibrated probabilistic product — as a
   benchmark for ours (doc 05).

## Proposed shape (options detailed in docs 01–05)

- **Collector**: GitHub Actions cron (public repo, free) committing gzipped raw JSON,
  idempotent by init-time so late/missed crons don't corrupt anything; Cloudflare
  Workers + R2 as the v2 if cron punctuality bites. ~5 MB/day raw, ~1 MB gzipped.
- **Storage**: raw JSON archive + one normalised long Parquet table
  `(source, model, location, init_time, valid_time, lead, variable, value, member, prob)`;
  DuckDB everywhere.
- **Evaluation**: CRPS (works for deterministic *and* ensemble sources), Brier +
  decomposition for rain probabilities, ETS for rain occurrence, all as skill scores vs
  climatology/persistence; reliability diagrams as the centrepiece; calibration error with
  confidence intervals via verified-uncertainty-calibration; Mondrian conformal per
  region×lead for guaranteed-coverage intervals.
- **Dashboard**: static site (Evidence or Observable Framework) on GitHub Pages reading
  metrics Parquet via DuckDB-WASM — zero runtime cost; UK map of station scorecards;
  segment explorer by region / lead / variable / season.
- **Week-1 unlock**: backfill 2.5 years from Previous Runs API and validate every metric
  choice on real data immediately, while the collector accumulates the unarchived sources.

## Decisions (settled 2026-07-04)

| # | Decision | Outcome |
|---|---|---|
| 1 | BBC | **Skip.** No scraping. |
| 2 | Met Office DataHub | **Signed up.** Key in `.env` as `MET_OFFICE_LAND_OBS_API_KEY` (git-ignored). Land Obs API probed and working. |
| 3 | OpenWeatherMap | **Deferred** (card-on-file requirement). |
| 4 | Data location | **In this repo**; migrate (R2/sibling repo) only if it gets out of hand. |
| 5 | Reliability score | Delegated: **CRPS skill score vs climatology as the headline, calibration-error ("honesty") axis beside it**, plain-English translation in tooltips. Justification in doc 03 §"Designing the reliability score". |
| 6 | Reading contact | Not for now. |
| 7 | Budget | **Strictly £0.** No paid tiers, no card-on-file services. |

## v1 scope (agreed)

**Met Office forecasts only, verified against UK observations.** Concretely:

- **Forecasts**: UKMO models via Open-Meteo (`ukmo_seamless` = UKV 2 km blended with UKMO
  global) — live, **plus Previous Runs backfill to ~Jan 2024**, plus MOGREPS ensemble
  members via the ensemble API (live-cache only, no archive).
  - Nuance worth remembering: Open-Meteo's UKMO feed is the **raw Met Office NWP model**,
    not the post-processed site-specific product behind the Met Office app. The DataHub
    site-specific API (free, 360 calls/day) is the app-like product — an easy v1.5 add
    using the existing DataHub account if we want "the model vs the product" comparisons.
- **Ground truth**: Met Office Land Obs (temp/wind/etc.) + EA rain gauges (amounts) +
  METAR (cross-check). All probed, all £0.
- Other model sources (ECMWF, ICON, GFS…) arrive later for free via the same Open-Meteo
  calls — the schema treats them as more values of `model`, so v1 should not hard-code
  UKMO anywhere except collector config.

## Docs index

- [01 — Data sources](01-data-sources.md): every free/paid source, ToS, probe results, ground truth strategy
- [02 — Prior art](02-prior-art.md): who does this already, what to reuse wholesale
- [03 — Metrics & calibration](03-metrics-and-calibration.md): CRPS/Brier/ETS, verified calibration, conformal, reliability-score options
- [04 — Architecture options](04-architecture-options.md): collector, storage, backfill, dashboard
- [05 — Costs](05-costs.md): the £0 path and where money goes later
- [`probes/`](../probes/README.md): runnable API probes + committed sample payloads
