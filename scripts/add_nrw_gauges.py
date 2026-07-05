"""One-off: add NRW rain gauges to Welsh stations in data/stations.json.

NRW's "River Level, Rainfall and Sea data" API (api.naturalresources.wales — open
data, but needs the free NRW_API_KEY subscription key) carries 15-min tipping-bucket
rainfall in mm for ~150 Welsh gauges: the Wales equivalent of EA/SEPA. Patches
nrw_gauge into the existing registry in place (non-Welsh stations get
nrw_gauge: null) — same rationale as add_sepa_gauges.py: no Met Office calls, no
station moves.

Uses one NRW call. Run: uv run scripts/add_nrw_gauges.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from build_station_registry import pick_nrw_gauge
from wpq.config import STATIONS_FILE
from wpq.fetchers import fetch_nrw_stations


def main() -> None:
    registry = json.loads(STATIONS_FILE.read_text())
    nrw_stations = fetch_nrw_stations()
    n_rain = sum(1 for s in nrw_stations
                 if any(p.get("paramNameEN") == "Rainfall" for p in s.get("parameters", [])))
    print(f"NRW stations: {len(nrw_stations)}, with a Rainfall parameter: {n_rain}")

    for station in registry["stations"]:
        if station.get("country") == "Wales":
            station["nrw_gauge"] = pick_nrw_gauge(station["lat"], station["lon"], nrw_stations)
            g = station["nrw_gauge"]
            print(f"  {station['seed_city']:<14} "
                  f"{'%s (%s) @%s km' % (g['name'], g['station_id'], g['distance_km']) if g else 'NO LIVE GAUGE'}")
        else:
            station["nrw_gauge"] = None

    STATIONS_FILE.write_text(json.dumps(registry, indent=1))
    n = sum(1 for s in registry["stations"] if s["nrw_gauge"])
    print(f"\nwrote {STATIONS_FILE}: {n} stations now carry an nrw_gauge")


if __name__ == "__main__":
    main()
