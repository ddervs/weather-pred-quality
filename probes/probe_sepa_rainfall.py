"""Probe SEPA's KiWIS time-series API for rain-gauge data (Scotland).

Keyless, Open Government Licence (attribute SEPA). ~380 tipping-bucket rain gauges
with 15-minute totals in mm via a KISTERS KiWIS endpoint (docs:
https://timeseriesdoc.sepa.org.uk). This is the Scotland equivalent of the EA
flood-monitoring gauges — it closes the "no rain-amount truth outside England" gap.
The older apps.sepa.org.uk/rainfall API is dead (DNS gone, checked 2026-07-05).

Probed 2026-07-05: values arrive within the hour; archives reach back to the 1990s
at many gauges; every one of our 6 Scottish stations has a live gauge within 15 km
(Edinburgh/Gogarbank is 0.2 km from the Met Office station). Gauges can go dormant
(Greenock stopped 2022-11) — liveness-check before pairing, as with EA.
getTimeseriesValues requires ts_id (not station_no), but accepts many ts_ids in one
call, so the whole Scottish network is a single collector request.

Run: uv run probes/probe_sepa_rainfall.py
"""

import requests

from locations import USER_AGENT

BASE = "https://timeseries.sepa.org.uk/KiWIS/KiWIS"
COMMON = {"service": "kisters", "type": "queryServices", "datasource": "0",
          "format": "json", "timezone": "UTC"}


def kiwis(request: str, **params) -> list:
    r = requests.get(BASE, params={**COMMON, "request": request, **params},
                     headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    return r.json()


def main() -> None:
    stations = kiwis("getStationList", parametertype_name="Precip",
                     returnfields="station_name,station_no,station_latitude,station_longitude")
    print(f"SEPA precipitation gauges: {len(stations) - 1}")

    # Edinburgh's nearest gauge: Gogarbank, 0.2 km from Met Office station gcvw5v
    ts = kiwis("getTimeseriesList", station_no="15196", ts_name="15minute.Total",
               parametertype_name="Precip",
               returnfields="station_name,ts_id,ts_unitsymbol,coverage")
    print("\nGogarbank 15-min Precip series:", ts[1])

    ts_id = ts[1][1]
    vals = kiwis("getTimeseriesValues", ts_id=ts_id, period="PT6H",
                 returnfields="Timestamp,Value", metadata="true",
                 md_returnfields="station_name,ts_unitsymbol")
    series = vals[0]
    print(f"\nlast 6h at {series['station_name']} (mm per 15-min interval):")
    for t, v in series["data"][-8:]:
        print(f"  {t}  {v}")

    print("\nNote: timestamps are interval-END (total for the preceding 15 min), same"
          " convention as EA; sum four slices for the Open-Meteo hourly window.")


if __name__ == "__main__":
    main()
