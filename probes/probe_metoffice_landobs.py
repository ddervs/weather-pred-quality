"""Probe the Met Office DataHub Land Observations API (free tier: 360 calls/day).

Uses MET_OFFICE_LAND_OBS_API_KEY from .env (never printed). Two endpoints:
  /observation-land/1/nearest?lat=..&lon=..   -> nearest station metadata (incl. geohash)
  /observation-land/1/{geohash}               -> last 48h hourly obs for that station

Checks: which stations sit nearest our probe locations, what parameters come back
(especially rainfall amounts), payload size, and hours of history per call.
Run: uv run probes/probe_metoffice_landobs.py   (11 API calls)
"""

import gzip
import json
from pathlib import Path

import requests

from locations import LOCATIONS, USER_AGENT

BASE = "https://data.hub.api.metoffice.gov.uk/observation-land/1"


def load_api_key() -> str:
    env = Path(__file__).parent.parent / ".env"
    for line in env.read_text().splitlines():
        line = line.strip()
        if line.startswith("MET_OFFICE_LAND_OBS_API_KEY"):
            return line.split("=", 1)[1].strip().strip("'\"")
    raise SystemExit("MET_OFFICE_LAND_OBS_API_KEY not found in .env")


def main() -> None:
    headers = {"apikey": load_api_key(), "User-Agent": USER_AGENT}

    print("nearest station per probe location:")
    stations = {}
    for name, lat, lon, region, _ in LOCATIONS:
        # API rejects >2dp coordinates with HTTP 400
        resp = requests.get(
            f"{BASE}/nearest",
            params={"lat": round(lat, 2), "lon": round(lon, 2)},
            headers=headers,
            timeout=30,
        )
        if resp.status_code != 200:
            print(f"  {name:<14} HTTP {resp.status_code}: {resp.text[:120]}")
            continue
        data = resp.json()
        st = data[0] if isinstance(data, list) and data else data
        stations[name] = st
        print(f"  {name:<14} -> {json.dumps(st)[:160]}")

    if "London" not in stations:
        raise SystemExit("no station found for London; cannot probe observations")

    st = stations["London"]
    geohash = st.get("geohash") or st.get("id")
    resp = requests.get(f"{BASE}/{geohash}", headers=headers, timeout=30)
    print(f"\nobservations for London station ({geohash}): status={resp.status_code}")
    resp.raise_for_status()
    raw = resp.content

    out = Path(__file__).parent / "samples" / "metoffice_landobs_london.json"
    out.parent.mkdir(exist_ok=True)
    out.write_bytes(raw)

    gz = len(gzip.compress(raw))
    print(f"payload: {len(raw):,} bytes raw, {gz:,} bytes gzipped (1 station)")

    data = resp.json()
    # Structure is unknown until probed; dump top-level shape and one record
    if isinstance(data, dict):
        print("top-level keys:", list(data.keys()))
        for key, value in data.items():
            if isinstance(value, list) and value:
                print(f"'{key}': {len(value)} entries; first entry:")
                print(json.dumps(value[0], indent=2)[:800])
                break
    elif isinstance(data, list):
        print(f"list of {len(data)} entries; first entry:")
        print(json.dumps(data[0], indent=2)[:800])
    print(f"\nsample saved to {out}")


if __name__ == "__main__":
    main()
