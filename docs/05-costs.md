# Costs: the £0 path and where money would eventually go

Prices checked 2026-07-03; Met Office from datahub.metoffice.gov.uk pricing pages, ex-VAT.

## The £0 path (covers everything in phase 1–2)

| Component | Provider | Free allowance | Our projected usage |
|---|---|---|---|
| Multi-model forecasts + ensembles + backfill | Open-Meteo | 10k calls/day (non-commercial) | ~40–100/day |
| Consumer forecast (Yr) | met.no | fair-use, keyless | ~200 light calls/day |
| Met Office site forecast | DataHub free tier | 360 calls/day | ≤300/day (50 sites × 2 × 3 products) |
| Ground truth obs | DataHub Land Obs free tier | 360 calls/day | depends on per-call scope (TBC) |
| Ground truth obs #2 | NOAA METAR | keyless | ~100/day |
| Scheduler + compute | GitHub Actions (public repo) | unlimited minutes | ~30 min/day |
| Storage | git repo (→ later R2 10 GB free) | ~5 GB soft / 10 GB | ~0.4 GB/yr gzipped |
| Dashboard hosting | GitHub Pages | 100 GB bandwidth/mo | tiny |
| Metrics/libs | scores, MAPIE, uncertainty-calibration, verif | OSS | — |

**Total: £0/mo**, with roughly 10× headroom in every quota at 50 locations. The binding
constraint is Met Office's 360 calls/day, which caps either site count or fetch frequency
for their products — not a blocker, just a design input.

Non-commercial caveat: Open-Meteo's free tier requires non-ad, non-subscription use. A
public hobby dashboard qualifies. If this ever grew ads/API customers: Open-Meteo API plans
start ~€29/mo, or self-host their AGPL stack.

## Where money would go, in order of likely temptation

1. **Met Office Blended Probabilistic (IMPROVER)** — their calibrated probabilistic product,
   i.e. the commercial version of our north star. £9/mo (550 calls/day) → £58/mo (4k) →
   £198/mo (14k). A £9 month would let us benchmark our calibration against theirs at ~10
   sites. The single most interesting paid data here.
2. **Met Office site-specific beyond free**: £9/mo (900/day) → £32/mo (3.6k/day) if we want
   hourly fetches at 100+ sites.
3. **VPS** (£3–6/mo, Hetzner/OVH class) if free-tier cron reliability annoys us.
4. **Cloudflare R2 beyond 10 GB**: $0.015/GB-mo (gridded phase; 100 GB ≈ $1.50/mo).
   Zero egress is the killer feature for a public DuckDB-WASM dashboard. Backblaze B2
   ($6/TB-mo) as archive tier.
5. **OpenWeatherMap**: 1,000 calls/day free but card-on-file; overage ~£0.001+/call
   (cap-able to £0). Only "cost" is the card requirement.
6. **Gridded phase egress/compute**: ECMWF open data is free on AWS/GCP/Azure mirrors;
   processing UK cutouts in Actions stays free; storing full-res UK grids (~1–5 GB/day raw
   GRIB subsets) would push storage to a few £/mo on R2/B2 within a year — the first real
   recurring cost on the north-star path.
7. **Not worth it / out of reach**: DTN (BBC's supplier) and ForecastWatch data are
   enterprise-sales-only (thousands/yr); Apple WeatherKit needs the £79/yr dev programme;
   AccuWeather paid tiers are US-consumer-oriented.

## Cost triggers to watch

- Repo > ~2 GB → move data layer to R2 (still £0 at our volumes).
- Locations > ~60 or hourly Met Office fetches → first £9/mo decision.
- Gridded UK maps → plan ~£2–5/mo storage within a year.
- Anything commercial (ads, API) → Open-Meteo paid/self-host + re-read every ToS.
