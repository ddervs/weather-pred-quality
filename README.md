# weather-pred-quality

Which UK weather forecast should you actually trust? This project caches forecasts from
multiple free sources (Met Office, Open-Meteo's per-model feeds, met.no/Yr, …), verifies
them against station observations, and scores providers on accuracy *and* honesty
(probabilistic calibration) — segmented by region, lead time, and weather variable.

North star: a UK map serving calibrated probabilistic forecasts with
conformal-prediction-backed reliability guarantees.

## Status: v1 collector live

- [`data/stations.json`](data/stations.json) — 33 health-checked verification locations
  (Met Office land-obs station + EA rain gauge + METAR airport triples)
- [`wpq/`](wpq/) — collector fetching UKMO forecasts + MOGREPS ensembles (via Open-Meteo),
  Met Office observations, EA rain gauges and METARs into `data/raw/` as gzipped JSON,
  every 6 h via [GitHub Actions](.github/workflows/collect.yml) (ensembles at 00Z/12Z)
- [`scripts/backfill_ukmo.py`](scripts/backfill_ukmo.py) — one-off 2024→now backfill of
  lead-stratified UKMO forecasts + ERA5 truth; [`scripts/smoke_metrics.py`](scripts/smoke_metrics.py)
  sanity-checks skill-vs-lead on it

Research docs are in [`docs/`](docs/):
start with [`docs/00-overview.md`](docs/00-overview.md) (TL;DR + decisions needed),
then data sources, prior art, metrics/calibration, architecture options, and costs.

[`probes/`](probes/) contains small runnable scripts that verified the key APIs
(Open-Meteo multi-model / previous-runs / ensembles, met.no, NOAA METAR) with sample
payloads committed under `probes/samples/`.

```sh
uv sync
uv run probes/probe_open_meteo_forecast.py
```
