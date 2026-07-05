# Research archive (2026-07-03/04)

The original research phase, preserved verbatim — including every source, tool and
architecture that was **considered but not (yet) adopted**: BBC scraping options,
OpenWeatherMap, met.no, Met Office site-specific product, the `scores`/MAPIE/verif
libraries, Cloudflare Workers, Evidence/Observable dashboards, gridded ECMWF open data,
paid tiers, and more. Nothing here is deleted when plans change, precisely so these
avenues can be picked up later.

**For how the system actually works today, read the living docs in
[`docs/`](../README.md) instead.** Where this archive and the living docs disagree, the
living docs win.

| Doc | Contents |
|---|---|
| [00-overview.md](00-overview.md) | Research TL;DR, the decisions table (settled 2026-07-04), agreed v1 scope |
| [01-data-sources.md](01-data-sources.md) | Every candidate data source: free/paid tiers, ToS, probe results, ground-truth options |
| [02-prior-art.md](02-prior-art.md) | Who does this already (ForecastAdvisor, Reading study, WeatherBench 2) and reusable OSS |
| [03-metrics-and-calibration.md](03-metrics-and-calibration.md) | Full metrics/calibration survey incl. options not implemented (CRPS, Elo, library choices) |
| [04-architecture-options.md](04-architecture-options.md) | Collector/storage/dashboard options A–D and why GitHub Actions git-scraping won |
| [05-costs.md](05-costs.md) | The £0 path and where money would go later |

The runnable API probes and sample payloads that informed all of this are in
[`probes/`](../../probes/README.md).
