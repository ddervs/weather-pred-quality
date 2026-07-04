"""Probe the Open-Meteo forecast API: multi-model, multi-location, one request.

Checks which per-model variables actually come back for UK locations and how big
the payload is, to size a caching job. Free non-commercial tier, no key.
Run: uv run probes/probe_open_meteo_forecast.py
"""

import gzip
import json
from pathlib import Path

import requests

from locations import LOCATIONS, USER_AGENT

MODELS = [
    "best_match",
    "ukmo_seamless",       # UK Met Office UKV + global
    "ecmwf_ifs025",        # ECMWF IFS 0.25 deg
    "icon_seamless",       # DWD ICON
    "gfs_seamless",        # NOAA GFS/HRRR blend
    "meteofrance_seamless",  # AROME/ARPEGE
    "metno_seamless",      # MET Norway (Nordic model only covers ~UK north?)
]

HOURLY = [
    "temperature_2m",
    "precipitation",
    "precipitation_probability",
    "rain",
    "snowfall",
    "wind_speed_10m",
    "wind_gusts_10m",
    "wind_direction_10m",
    "cloud_cover",
    "relative_humidity_2m",
    "surface_pressure",
]

DAILY = [
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "precipitation_probability_max",
    "wind_speed_10m_max",
]


def main() -> None:
    lats = ",".join(str(lat) for _, lat, _, _, _ in LOCATIONS)
    lons = ",".join(str(lon) for _, _, lon, _, _ in LOCATIONS)
    params = {
        "latitude": lats,
        "longitude": lons,
        "hourly": ",".join(HOURLY),
        "daily": ",".join(DAILY),
        "models": ",".join(MODELS),
        "forecast_days": "8",
        "timezone": "UTC",
    }
    resp = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=60,
    )
    print(f"status={resp.status_code} url_len={len(resp.url)}")
    resp.raise_for_status()
    raw = resp.content
    data = resp.json()

    out = Path(__file__).parent / "samples" / "open_meteo_forecast.json"
    out.parent.mkdir(exist_ok=True)
    out.write_bytes(raw)

    n_locs = len(data) if isinstance(data, list) else 1
    gz = len(gzip.compress(raw))
    print(f"locations returned: {n_locs}")
    print(f"payload: {len(raw):,} bytes raw, {gz:,} bytes gzipped "
          f"({len(raw) / n_locs:,.0f} B/location raw)")

    first = data[0] if isinstance(data, list) else data
    hourly_keys = sorted(first.get("hourly", {}).keys())
    print("\nhourly keys for location[0] (suffix = model):")
    # Group by variable: which models returned values (vs all-null)?
    per_model: dict[str, dict[str, bool]] = {}
    for key in hourly_keys:
        if key == "time":
            continue
        base, model = key, "best_match"
        for m in MODELS:
            if key.endswith(f"_{m}"):
                base, model = key[: -(len(m) + 1)], m
                break
        vals = first["hourly"][key]
        has_data = any(v is not None for v in vals)
        per_model.setdefault(base, {})[model] = has_data
    width = max(len(v) for v in per_model)
    header = " " * width + "  " + "  ".join(f"{m[:12]:>12}" for m in MODELS)
    print(header)
    for var, models in sorted(per_model.items()):
        row = "  ".join(f"{str(models.get(m, '-')):>12}" for m in MODELS)
        print(f"{var:<{width}}  {row}")

    n_hours = len(first["hourly"]["time"])
    print(f"\nhourly steps: {n_hours} (requested 8 days)")
    print(f"sample saved to {out}")


if __name__ == "__main__":
    main()
