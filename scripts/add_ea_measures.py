"""One-off: pin each EA gauge's LIVE rainfall series into data/stations.json.

Adds `measure` (EA measure-id tail) and `period` (900 or 3600 s) to every
`ea_gauge` entry so the collector fetches exactly one series per gauge and the
normaliser knows hourly gauges from 15-min ones. Why (found 2026-07-06): two of
our gauges (Cambridge E5731, Lincoln E5721) are hourly-only - the 4-slice rule
silently discarded ALL their readings; six more publish a second rainfall
series (intensity / `rainfall-water`) that doubled the row rate, truncating the
30 h fetch window - and at four of those the *totals* series is dormant and the
twin is the live one, so selection is by reading freshness, not name.

build_station_registry.py does the same for future registry rebuilds.
Run once: uv run scripts/add_ea_measures.py
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wpq.config import STATIONS_FILE
from wpq.fetchers import fetch_ea_rain_measure


def main() -> None:
    registry = json.loads(STATIONS_FILE.read_text())
    for station in registry["stations"]:
        gauge = station.get("ea_gauge")
        if not gauge:
            continue
        measure = fetch_ea_rain_measure(gauge["station_reference"])
        if measure is None:
            print(f"{station['seed_city']:15} {gauge['station_reference']:8} "
                  "NO LIVE RAINFALL SERIES - left unpinned")
            continue
        gauge.update(measure)
        print(f"{station['seed_city']:15} {gauge['station_reference']:8} "
              f"period={measure['period']:4} {measure['measure']}")
        time.sleep(0.2)
    STATIONS_FILE.write_text(json.dumps(registry, indent=1))
    print(f"updated {STATIONS_FILE}")


if __name__ == "__main__":
    main()
