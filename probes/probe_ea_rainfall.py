"""Probe the Environment Agency flood-monitoring API for rain-gauge data (England).

Keyless, Open Government Licence, 15-minute tipping-bucket rainfall in mm.
This fills the gap left by the Met Office Land Observations API, which (probed
2026-07-04) carries NO rainfall-amount parameter on the free tier.
Scotland/Wales equivalents: SEPA API, Natural Resources Wales (not probed).
Run: uv run probes/probe_ea_rainfall.py
"""

import json

import requests

from locations import USER_AGENT

BASE = "https://environment.data.gov.uk/flood-monitoring"


def main() -> None:
    headers = {"User-Agent": USER_AGENT}

    # Gauge density check near central London
    r = requests.get(
        f"{BASE}/id/stations",
        params={"parameter": "rainfall", "lat": 51.5072, "long": -0.1276, "dist": 15},
        headers=headers,
        timeout=30,
    )
    r.raise_for_status()
    stations = r.json()["items"]
    print(f"rainfall gauges within 15 km of central London: {len(stations)}")

    # Latest readings across the network (proves liveness + units)
    r = requests.get(
        f"{BASE}/data/readings",
        params={"parameter": "rainfall", "latest": "", "_limit": 10},
        headers=headers,
        timeout=30,
    )
    r.raise_for_status()
    items = r.json()["items"]
    print("\nlatest readings sample (value = mm per 15-min interval):")
    for it in items[:5]:
        print(f"  {it.get('dateTime')}  {it.get('value')} mm  {it.get('measure', '')[-55:]}")

    print("\nNote: individual gauges can be dormant; a collector should pick gauges with"
          " recent readings, and expect QC quirks (tipping buckets under-catch in wind/snow).")


if __name__ == "__main__":
    main()
