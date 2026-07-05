"""Probe NRW's River Level, Rainfall and Sea data API for rain-gauge data (Wales).

Open data, but needs NRW_API_KEY in .env — a free subscription key from
https://api-portal.naturalresources.wales (Azure APIM; key goes in the
Ocp-Apim-Subscription-Key header). ~150 of ~409 monitoring stations carry a
Rainfall parameter: 15-min tipping-bucket totals in mm, live within ~30 min.
Completes the GB rain-amounts truth alongside EA (England) and SEPA (Scotland).

Probed 2026-07-05 with a real key. Gotchas that cost time:
- statusEN says "Online" even for gauges dead since 2023 — liveness is the
  Rainfall parameter's latestTime.
- Rainfall parameter IDs are PER-STATION (e.g. Llantwit Major 10232, Llyn Cefni
  10122), from the parameters[] list in /StationData.
- /StationData/historical returns a FULL YEAR (~35k readings, 1.5 MB) unless
  windowed with `from`/`to` (dates, `to` end-exclusive) — the only params it honours.

Run: uv run probes/probe_nrw_rainfall.py
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from locations import USER_AGENT

sys.path.insert(0, str(Path(__file__).parent.parent))
from wpq.config import get_env  # noqa: E402

BASE = "https://api.naturalresources.wales/rivers-and-seas/v1/api"


def main() -> None:
    headers = {"Ocp-Apim-Subscription-Key": get_env("NRW_API_KEY"),
               "User-Agent": USER_AGENT}

    r = requests.get(f"{BASE}/StationData", headers=headers, timeout=60)
    r.raise_for_status()
    stations = r.json()
    rain = [s for s in stations
            if any(p.get("paramNameEN") == "Rainfall" for p in s.get("parameters", []))]
    print(f"NRW stations: {len(stations)}, with a Rainfall parameter: {len(rain)}")

    # Bangor's nearest gauge: Llyn Cefni on Anglesey, 3.2 km from station gckyur
    now = datetime.now(timezone.utc)
    r = requests.get(f"{BASE}/StationData/historical",
                     params={"location": "1027", "parameter": "10122",
                             "from": (now - timedelta(hours=6)).date().isoformat(),
                             "to": (now + timedelta(days=1)).date().isoformat()},
                     headers=headers, timeout=60)
    r.raise_for_status()
    obj = r.json()
    readings = obj["parameterReadings"]
    print(f"\n{obj['nameEN']} ({obj['units']} per 15-min interval), last 8 of {len(readings)}:")
    for item in readings[-8:]:
        print(f"  {item['time']}  {item['value']}")

    print("\nNote: timestamps are interval-END, same convention as EA/SEPA; sum four"
          " slices for the Open-Meteo hourly window.")


if __name__ == "__main__":
    main()
