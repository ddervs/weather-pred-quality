# Architecture options: collect → store → evaluate → show

Constraint set: £0 budget, free-tier cloud cron preferred, ~50 UK station-located points,
data volumes from probes (~5 MB/day raw JSON total, ~1 MB/day gzipped).

## The one insight that shapes everything

Sources split by **whether missing a fetch loses data forever**:

| Source | Archived upstream? | Collector reliability needed |
|---|---|---|
| Open-Meteo deterministic models | ✅ Previous Runs API (back to ~2024) | *Low* — anything missed is backfillable |
| Open-Meteo **ensembles** | ❌ | High — the only truly unrecoverable forecast data |
| met.no | ❌ | High (per-run capture) |
| Met Office DataHub site-specific | ❌ | High |
| METAR obs | 15-day API lookback (+ NOAA archives) | Low-ish |
| Met Office Land Obs | recent-only | High-ish |

So the collector's job is really: **capture the non-archived sources reliably; treat
Open-Meteo deterministic data as backfillable gravy.** And v0 of the *evaluation* needs no
collector at all — 2.5 years of Previous-Runs history is available today, which means the
dashboard can be built and validated against real multi-year data in week 1 while the
collector quietly accumulates the rest.

## Option A — GitHub Actions git-scraping (recommended start)

Scheduled workflow (cron every 3–6 h) fetches all sources, commits gzipped JSON to the repo
(or a sibling `weather-pred-data` repo to keep this one clean).

- **Cost**: £0. Public repos get unlimited free Actions minutes; a fetch run is <1 min.
- **Known wart**: GH cron fires late (5–30 min) and occasionally skips under load.
  Mitigations: (a) schedule 2× more often than strictly needed and key everything by
  `(source, init_time/valid_time)` so runs are idempotent; (b) fetch-time stamping is
  irrelevant for correctness because every payload carries its own init/valid times;
  (c) `workflow_dispatch` for manual catch-up; (d) missed met.no runs cost one 30-min-expiry
  snapshot, tolerable at 3 h cadence.
- **Secrets**: DataHub key as an Actions secret. Fine.
- **Repo growth**: ~1 MB/day gzipped → ~400 MB/yr of history. Git handles it; GitHub soft
  limits ~5 GB. Years of runway; consolidate to Parquet + prune (or move data repo to
  R2/HF datasets) when it hurts.
- Proven pattern (Simon Willison's git-scraping; hundreds of public examples).

## Option B — Cloudflare Workers cron + R2

Workers free tier: 100k req/day, cron triggers fire *reliably on time*; R2 free: 10 GB,
no egress fees. Write gzipped JSON straight to R2; dashboard reads Parquet from R2 (free
egress → DuckDB-WASM can query it directly over HTTP range requests).

- Pro: proper cron punctuality, storage decoupled from git, scales to gridded phase.
- Con: JS/TS runtime for the fetcher (or Python Workers, still beta-ish), a second platform,
  slightly more setup; observability worse than a green/red Actions tab.

## Option C — machine you own (Mac/Pi cron) / Option D — VPS (£3–6/mo)

C: free, trivially debuggable, but ties collection to a box staying on — overnight laptop
sleep = holes in exactly the unrecoverable sources. D: boring and reliable but violates the
£0 constraint; keep as the fallback if free tiers annoy us.

**Recommendation**: A now (velocity, visibility), with the layout kept
platform-agnostic (a plain `collect.py` that a Worker/VPS could also run), reassess if cron
punctuality actually bites. B is the natural v2 and the gridded-phase home.

## Storage layout (applies to any option)

Two layers, ForecastOps/WeatherBench-style:

1. **Raw immutable archive** (audit trail, reprocessable):
   `raw/{source}/{YYYY-MM-DD}/{fetch_ts}.json.gz`
2. **Normalised long table**, nightly job, monthly Parquet partitions:
   `norm/source=…/month=…/part.parquet` with columns
   `(source, model, location_id, init_time, valid_time, lead_hours, variable, value, member, prob)`
   — one schema fits deterministic, ensemble (member) and probability (prob) data.
   Observations land in the same shape with `source='obs_metoffice'`, `lead_hours=0`.
3. Metrics job (weekly + on-demand) joins norm×obs → `metrics/` Parquet, small enough to
   ship to the dashboard whole.

DuckDB is the query engine everywhere (local analysis, CI jobs, and in-browser via WASM).
SQLite optional for the location/station registry. Volumes: norm layer ≈ 25–40 MB/month
Parquet at 50 locations — negligible.

## Backfill plan (week 1, one-off)

Previous-Runs + Historical-Forecast APIs → 50 stations × 7 models × 3 vars × leads 0–7 d
back to Jan 2024, ~a few hundred API calls spread over a couple of days (well inside free
limits) → instant 2.5-year verification dataset. ERA5 + METAR/MIDAS for matching truth.
This de-risks every metric decision before the collector has a week of data.

## Dashboard options (map + segment explorer)

| Option | What it is | Fit |
|---|---|---|
| **Observable Framework** | static-site generator, first-class DuckDB-WASM + Plot; deploy GH Pages | **Best for the map-centric north star**; JS-forward |
| **Evidence.dev** | markdown + SQL → static BI site | Fastest respectable v1; map support basic (choropleth-ish); great for metric tables/reliability charts |
| **Datasette (+ datasette-cluster-map)** | publish SQLite, explore/filter | Great *exploration* companion, weak as a polished public dashboard |
| **Streamlit/Marimo (Community Cloud)** | Python app | Fast to build, but a running server, sleeps on free tier, not static — misfit for public artifact |
| **Hand-rolled MapLibre + DuckDB-WASM on GH Pages** | full control | The north-star endpoint; most work |

Recommended trajectory: **Evidence or Observable static site on GH Pages reading the
metrics Parquet** for v1 (segment tables, reliability diagrams, lead-time curves, simple UK
choropleth by region), evolving toward MapLibre station-dot map with per-station scorecards.
Static + Parquet + WASM means the dashboard has zero runtime cost forever.

## Failure modes worth designing for (cheap insurance now)

- **Provider schema drift**: raw layer + versioned normalisers; alert on parse failure
  (Actions → email is built in).
- **Station outages/QC**: never single-source truth for a location if avoidable; flag obs
  gaps rather than silently scoring against ERA5.
- **Timezone/DST bugs**: everything UTC internally, convert at display only. (Classic
  verification-project killer.)
- **Forecast-jump artefacts**: score *runs* (init_time), never "latest at fetch time";
  our schema already enforces this.
