"""One-off: add SEPA rain gauges to Scottish stations in data/stations.json.

SEPA's KiWIS time-series API (timeseries.sepa.org.uk — keyless, OGL) carries 15-min
tipping-bucket rainfall in mm for ~380 Scottish gauges: the Scotland equivalent of
the EA gauges England stations already have. This patches sepa_gauge into the
existing registry in place (non-Scottish stations get sepa_gauge: null) so we don't
re-run the full registry build — that would spend Met Office API calls and risk
moving stations, breaking time-series continuity.

Uses zero Met Office calls (~10 SEPA calls). Run: uv run scripts/add_sepa_gauges.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from build_station_registry import pick_sepa_gauge
from wpq.config import STATIONS_FILE
from wpq.fetchers import fetch_sepa_precip_stations


def main() -> None:
    registry = json.loads(STATIONS_FILE.read_text())
    sepa_gauges = fetch_sepa_precip_stations()
    print(f"SEPA precip gauges available: {len(sepa_gauges)}")

    for station in registry["stations"]:
        if station.get("country") == "Scotland":
            station["sepa_gauge"] = pick_sepa_gauge(station["lat"], station["lon"], sepa_gauges)
            g = station["sepa_gauge"]
            print(f"  {station['seed_city']:<14} "
                  f"{'%s (%s) @%s km' % (g['name'], g['station_no'], g['distance_km']) if g else 'NO LIVE GAUGE'}")
        else:
            station["sepa_gauge"] = None

    STATIONS_FILE.write_text(json.dumps(registry, indent=1))
    n = sum(1 for s in registry["stations"] if s["sepa_gauge"])
    print(f"\nwrote {STATIONS_FILE}: {n} stations now carry a sepa_gauge")


if __name__ == "__main__":
    main()
