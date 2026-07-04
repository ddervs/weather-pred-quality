"""Probe the Open-Meteo Previous Runs API: same forecast valid time, different lead times.

If this works well, historical lead-time-stratified forecasts back to ~Jan 2024 are
available WITHOUT us having cached anything — a huge head start for verification.
Run: uv run probes/probe_open_meteo_previous_runs.py
"""

import gzip
import json
from pathlib import Path

import requests

from locations import USER_AGENT

MODELS = ["ukmo_seamless", "ecmwf_ifs025", "icon_seamless", "gfs_seamless"]

# temperature + precipitation at lead times 0..5 days before valid time
VARS = ["temperature_2m", "precipitation", "wind_speed_10m"]
LEADS = range(6)  # previous_day0 .. previous_day5


def main() -> None:
    hourly = [f"{v}_previous_day{d}" for v in VARS for d in LEADS]
    params = {
        "latitude": "51.5072",
        "longitude": "-0.1276",
        "hourly": ",".join(hourly),
        "models": ",".join(MODELS),
        "past_days": "3",
        "forecast_days": "1",
        "timezone": "UTC",
    }
    resp = requests.get(
        "https://previous-runs-api.open-meteo.com/v1/forecast",
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=60,
    )
    print(f"status={resp.status_code}")
    resp.raise_for_status()
    raw = resp.content
    data = resp.json()

    out = Path(__file__).parent / "samples" / "open_meteo_previous_runs.json"
    out.parent.mkdir(exist_ok=True)
    out.write_bytes(raw)

    gz = len(gzip.compress(raw))
    print(f"payload: {len(raw):,} bytes raw, {gz:,} bytes gzipped "
          f"(1 location, {len(MODELS)} models, {len(VARS)} vars x {len(LEADS)} leads, 4 days)")

    first = data[0] if isinstance(data, list) else data
    times = first["hourly"]["time"]
    print(f"time range: {times[0]} .. {times[-1]} ({len(times)} steps)")

    # Show how the same valid hour differs across lead times (temperature, first model)
    print("\nLondon temperature_2m at a fixed valid hour, by lead time (per model):")
    idx = 12  # some hour comfortably in the past
    print(f"valid time: {times[idx]}")
    for key in sorted(first["hourly"].keys()):
        if key.startswith("temperature_2m_previous_day"):
            val = first["hourly"][key][idx]
            print(f"  {key:<55} {val}")
    print(f"\nsample saved to {out}")


if __name__ == "__main__":
    main()
