"""Probe aviationweather.gov METAR API as a keyless ground-truth observation source.

UK airport METARs: hourly/half-hourly observations of temperature, wind, visibility,
precipitation codes, cloud. Public NOAA endpoint, JSON, max 100 req/min.
Run: uv run probes/probe_metar.py
"""

import gzip
import json
from pathlib import Path

import requests

from locations import LOCATIONS, USER_AGENT


def main() -> None:
    icaos = sorted({icao for *_, icao in LOCATIONS})
    resp = requests.get(
        "https://aviationweather.gov/api/data/metar",
        params={"ids": ",".join(icaos), "format": "json", "hours": "3"},
        headers={"User-Agent": USER_AGENT},
        timeout=60,
    )
    print(f"status={resp.status_code}")
    resp.raise_for_status()
    raw = resp.content
    data = resp.json()

    out = Path(__file__).parent / "samples" / "metar_uk.json"
    out.parent.mkdir(exist_ok=True)
    out.write_bytes(raw)

    gz = len(gzip.compress(raw))
    print(f"payload: {len(raw):,} bytes raw, {gz:,} bytes gzipped, {len(data)} observations "
          f"for {len(icaos)} stations x 3h")

    by_station: dict[str, int] = {}
    for ob in data:
        by_station[ob.get("icaoId", "?")] = by_station.get(ob.get("icaoId", "?"), 0) + 1
    print("obs per station (3h window):", by_station)

    if data:
        sample = data[0]
        keep = ["icaoId", "reportTime", "temp", "dewp", "wdir", "wspd", "wgst",
                "visib", "altim", "wxString", "precip", "pcp3hr", "clouds", "rawOb"]
        print("\nfirst observation (selected fields):")
        print(json.dumps({k: sample.get(k) for k in keep}, indent=2, default=str))
    print(f"\nsample saved to {out}")


if __name__ == "__main__":
    main()
