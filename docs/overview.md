# Overview: what this project is and how it works

*Living doc. Last updated 2026-07-05.*

## The question

**Which UK weather forecast should you actually trust — and how far ahead?**

Every day, forecast providers publish predictions for tomorrow, the day after, and up to
two weeks out. Almost nobody systematically checks, after the fact, how right they were.
This project does that check for the UK: it records what was *forecast*, records what
actually *happened* at weather stations, and scores the difference — broken down by
region, weather variable (temperature, rain, wind), and **lead time** (how far in advance
the forecast was made; a "day-3 forecast" was issued three days before the weather it
describes).

The north star is a UK map serving *calibrated probabilistic* forecasts — "there's a 70 %
chance of rain, and when we say 70 % it really rains 70 % of the time" — with statistical
coverage guarantees (conformal prediction). The current phase is the necessary
foundation: verify one provider's forecasts honestly.

## Scope right now (v1)

- **One forecast provider**: the UK Met Office's own numerical weather model
  ("UKMO", fetched via the free Open-Meteo API), both its single best-guess forecast and
  its MOGREPS ensemble (many parallel runs that express uncertainty).
- **33 fixed verification locations** across England, Scotland, Wales and Northern
  Ireland, each anchored at a real observation station (see
  [data-sources.md](data-sources.md)).
- **Ground truth**: real station observations (Met Office land stations, EA/SEPA/NRW
  rain gauges covering England, Scotland and Wales, airport METAR reports), plus the
  ERA5 reanalysis as an interim stand-in while live observations accumulate.
- **Budget: strictly £0.** Free API tiers only, polite usage, GitHub Actions for compute,
  the git repo itself for storage.
- Other providers (ECMWF, ICON, GFS, met.no, the Met Office *app* product…) are designed
  for but deliberately deferred — the schema treats them as more values of a `model`
  column. The research on all of them is preserved in [research/](research/).

## How the pipeline fits together

```
                    every 6 h (GitHub Actions: collect.yml)
  Open-Meteo (UKMO forecast + ensemble) ─┐
  Met Office land observations ──────────┤
  EA/SEPA/NRW rain gauges ───────────────┼──►  data/raw/{source}/{date}/{HHMM}Z.json.gz
  METAR airport reports ─────────────────┘        (immutable gzipped JSON archive)

                    one-off backfill (scripts/backfill_ukmo.py)
  Open-Meteo Previous Runs (UKMO, leads 0–5 d) ──►  data/backfill/prev_runs/
  Open-Meteo Archive (ERA5 truth) ───────────────►  data/backfill/era5/
        (2.5 years of history, 2024-01 → 2026-06, available before we cached anything)

                    weekly (GitHub Actions: metrics.yml)
  raw + backfill ──► wpq/normalize.py ──► data/norm/*.parquet   (tidy tables, one schema,
                                                                 all unit conversion here)
  norm ──► wpq/metrics.py ────► data/metrics/metrics.parquet    (accuracy scores)
  norm ──► wpq/calibration.py ► data/metrics/{conformal,brier_decomposition,
                                              bootstrap_ci}.parquet
  metrics ──► scripts/make_dashboard.py ──► docs/dashboard.html (static, self-contained)
```

Two properties worth knowing:

- **Raw is immutable, everything downstream is a deterministic rebuild.** The normalised
  tables (`data/norm/`) are gitignored and rebuilt from raw in ~35 s; only raw data and
  final metrics are committed.
- **Missing a collection run is mostly harmless.** Open-Meteo archives past forecast runs
  (the Previous Runs API), so deterministic forecasts are back-fillable. The things that
  genuinely need live capture are the ensemble members and the station observations.

## What it has found so far

Dated details in [results/](results/); headlines as of 2026-07-05 (all vs ERA5 truth,
2024-01 → 2026-06, 33 stations):

- **Temperature**: UKMO is typically off by 0.70 °C same-day, degrading to 1.63 °C at
  five days ahead. It beats "guess the seasonal average" (climatology) at every lead, but
  by day 5 the margin is only ~7 %.
- **Wind**: UKMO's hourly 10 m wind forecast *loses* to climatology beyond day ~3 —
  "typical wind for this station and time of year" is the better bet at long lead.
- **Rain**: as a yes/no call, the forecast has *negative* skill versus just quoting the
  ~23 % base rate from day 2 onward — packaging a probability as certainty destroys its
  value. This is the core argument for probabilistic (PoP) forecasts, coming when enough
  ensemble data has accumulated (~2026-08).
- **Trustworthy intervals exist**: conformal prediction calibrated on 2024 achieves its
  promised 90 % coverage on 2025–26 data in every nation × lead cell — "tomorrow's
  forecast is good to ±1.7 °C, day-5 only to ±3.6 °C" as a guarantee, not an average.

## Status and what's next

Collector live since 2026-07-04; backfill, metrics and calibration layers done; the v1
dashboard is the current chunk. The repo is private for now; publishing (GitHub Pages)
comes only once everything works privately. The always-current plan is
[PLAN.md](PLAN.md).
