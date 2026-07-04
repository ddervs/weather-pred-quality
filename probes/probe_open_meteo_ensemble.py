"""Probe the Open-Meteo Ensemble API: raw ensemble members for UK locations.

Ensemble members are the raw material for CRPS and calibrated probabilities —
if MOGREPS (UKMO), ECMWF ENS and ICON-EPS members are available per UK point,
we can build full predictive distributions rather than single point forecasts.
Run: uv run probes/probe_open_meteo_ensemble.py
"""

import gzip
from pathlib import Path

import requests

from locations import USER_AGENT

MODELS = [
    "ukmo_global_ensemble_20km",  # MOGREPS-G
    "ukmo_uk_ensemble_2km",       # MOGREPS-UK (high-res, UK only)
    "ecmwf_ifs025",               # ECMWF ENS 51 members
    "icon_eu_eps",                # DWD ICON-EU EPS
    "gfs025",                     # NOAA GEFS
]


def main() -> None:
    params = {
        "latitude": "51.5072",
        "longitude": "-0.1276",
        "hourly": "temperature_2m,precipitation,wind_speed_10m",
        "models": ",".join(MODELS),
        "forecast_days": "5",
        "timezone": "UTC",
    }
    resp = requests.get(
        "https://ensemble-api.open-meteo.com/v1/ensemble",
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=60,
    )
    print(f"status={resp.status_code}")
    resp.raise_for_status()
    raw = resp.content
    data = resp.json()

    out = Path(__file__).parent / "samples" / "open_meteo_ensemble.json"
    out.parent.mkdir(exist_ok=True)
    out.write_bytes(raw)

    gz = len(gzip.compress(raw))
    print(f"payload: {len(raw):,} bytes raw, {gz:,} bytes gzipped "
          f"(1 location, {len(MODELS)} ensembles, 3 vars, 5 days)")

    first = data[0] if isinstance(data, list) else data
    keys = [k for k in first["hourly"] if k != "time"]
    # Count members per model for temperature
    counts: dict[str, int] = {}
    for k in keys:
        if not k.startswith("temperature_2m"):
            continue
        for m in MODELS:
            if k.endswith(m) or m in k:
                counts[m] = counts.get(m, 0) + 1
                break
    print("temperature_2m member count per ensemble model:")
    for m in MODELS:
        print(f"  {m:<28} {counts.get(m, 0)}")
    print(f"sample saved to {out}")


if __name__ == "__main__":
    main()
