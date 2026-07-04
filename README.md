# weather-pred-quality

Which UK weather forecast should you actually trust? This project caches forecasts from
multiple free sources (Met Office, Open-Meteo's per-model feeds, met.no/Yr, …), verifies
them against station observations, and scores providers on accuracy *and* honesty
(probabilistic calibration) — segmented by region, lead time, and weather variable.

North star: a UK map serving calibrated probabilistic forecasts with
conformal-prediction-backed reliability guarantees.

## Status: research phase

No pipeline exists yet. The research deliverables are in [`docs/`](docs/):
start with [`docs/00-overview.md`](docs/00-overview.md) (TL;DR + decisions needed),
then data sources, prior art, metrics/calibration, architecture options, and costs.

[`probes/`](probes/) contains small runnable scripts that verified the key APIs
(Open-Meteo multi-model / previous-runs / ensembles, met.no, NOAA METAR) with sample
payloads committed under `probes/samples/`.

```sh
uv sync
uv run probes/probe_open_meteo_forecast.py
```
