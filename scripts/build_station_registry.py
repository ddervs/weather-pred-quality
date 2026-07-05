"""Build data/stations.json: the fixed location registry for verification.

For ~35 seed cities across UK regions:
  1. find the nearest Met Office land-obs station (geohash) and health-check it
     (>=40 of 48 hourly entries must carry a temperature),
  2. pair it with the nearest *live* EA rain gauge (England only; readings in last 24h),
  3. pair Scottish stations with the nearest *live* SEPA rain gauge (15-min Precip
     series with data in the last 24h — dormant gauges are skipped),
  4. pair Welsh stations with the nearest *live* NRW rain gauge (same 24h rule;
     needs NRW_API_KEY),
  5. pair it with the nearest METAR airport within 40 km.

Stations failing the health check are dropped. Locations are the *station* positions
(decoded geohash centres), not the city centres. Run once; re-run only deliberately —
moving stations breaks time-series continuity.

Uses ~70 Met Office API calls (budget: 360/day). Run: uv run scripts/build_station_registry.py
"""

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from wpq.config import STATIONS_FILE
from wpq.fetchers import (
    fetch_ea_gauges_near,
    fetch_ea_readings,
    fetch_land_obs,
    fetch_metar,
    fetch_nearest_land_station,
    fetch_nrw_stations,
    fetch_sepa_precip_stations,
    fetch_sepa_ts_meta,
)
from wpq.geo import geohash_decode, haversine_km

SEED_CITIES = [
    # central-London station (gcpvj0) is dud; use Heathrow + Greenwich to anchor London
    ("London-Heathrow", 51.4775, -0.4614), ("London-Greenwich", 51.4769, 0.0005),
    ("Birmingham", 52.4862, -1.8904),
    ("Manchester", 53.4808, -2.2426), ("Leeds", 53.8008, -1.5491),
    ("Sheffield", 53.3811, -1.4701), ("Newcastle", 54.9783, -1.6178),
    ("Liverpool", 53.4084, -2.9916), ("Bristol", 51.4545, -2.5879),
    ("Nottingham", 52.9548, -1.1581), ("Southampton", 50.9097, -1.4044),
    ("Brighton", 50.8225, -0.1372), ("Plymouth", 50.3755, -4.1427),
    ("Exeter", 50.7260, -3.5275), ("Norwich", 52.6309, 1.2974),
    ("Cambridge", 52.2053, 0.1218), ("Oxford", 51.7520, -1.2577),
    ("Hull", 53.7676, -0.3274), ("York", 53.9600, -1.0873),
    ("Carlisle", 54.8925, -2.9329), ("Cardiff", 51.4816, -3.1791),
    ("Swansea", 51.6214, -3.9436), ("Aberystwyth", 52.4153, -4.0829),
    ("Bangor", 53.2274, -4.1293), ("Edinburgh", 55.9533, -3.1883),
    ("Glasgow", 55.8642, -4.2518), ("Aberdeen", 57.1497, -2.0943),
    ("Inverness", 57.4778, -4.2247), ("Fort William", 56.8198, -5.1052),
    ("Stornoway", 58.2094, -6.3866), ("Belfast", 54.5973, -5.9301),
    ("Derry", 54.9966, -7.3086), ("Penzance", 50.1186, -5.5371),
    ("Dover", 51.1279, 1.3134), ("Lincoln", 53.2307, -0.5406),
    ("Shrewsbury", 52.7069, -2.7527),
]

# UK METAR airports (ICAO, lat, lon) for cross-check pairing
METAR_AIRPORTS = [
    ("EGLL", 51.4775, -0.4614), ("EGKK", 51.1481, -0.1903), ("EGSS", 51.8850, 0.2350),
    ("EGBB", 52.4539, -1.7480), ("EGCC", 53.3537, -2.2750), ("EGNM", 53.8659, -1.6606),
    ("EGNT", 55.0375, -1.6917), ("EGGP", 53.3336, -2.8497), ("EGGD", 51.3827, -2.7191),
    ("EGHI", 50.9503, -1.3568), ("EGKA", 50.8356, -0.2972), ("EGHD", 50.4228, -4.1058),
    ("EGTE", 50.7344, -3.4139), ("EGSH", 52.6758, 1.2828), ("EGSC", 52.2050, 0.1750),
    ("EGNX", 52.8311, -1.3281), ("EGNJ", 53.5744, -0.3508), ("EGNV", 54.5092, -1.4294),
    ("EGFF", 51.3967, -3.3433), ("EGPH", 55.9500, -3.3725), ("EGPF", 55.8719, -4.4331),
    ("EGPD", 57.2019, -2.1978), ("EGPE", 57.5425, -4.0475), ("EGPO", 58.2156, -6.3311),
    ("EGAA", 54.6575, -6.2158), ("EGAE", 55.0428, -7.1611), ("EGHC", 50.1028, -5.6706),
    ("EGMD", 50.9561, 0.9392), ("EGXW", 53.1662, -0.5238), ("EGOS", 52.7981, -2.6681),
]


def pick_live_gauge(lat: float, lon: float) -> dict | None:
    """Nearest EA gauge with a reading in the last 24h (England only in practice)."""
    gauges = fetch_ea_gauges_near(lat, lon)
    with_pos = [g for g in gauges if g.get("lat") and g.get("long")]
    with_pos.sort(key=lambda g: haversine_km(lat, lon, g["lat"], g["long"]))
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    for gauge in with_pos[:4]:
        ref = gauge.get("stationReference")
        if not ref:
            continue
        try:
            readings = fetch_ea_readings(ref, limit=4).get("items", [])
        except Exception:
            continue
        fresh = any(
            datetime.fromisoformat(r["dateTime"].replace("Z", "+00:00")) > cutoff
            for r in readings if r.get("dateTime")
        )
        if fresh:
            return {
                "station_reference": ref,
                "lat": gauge["lat"],
                "lon": gauge["long"],
                "distance_km": round(haversine_km(lat, lon, gauge["lat"], gauge["long"]), 1),
            }
        time.sleep(0.2)
    return None


def pick_sepa_gauge(lat: float, lon: float, gauges: list[dict]) -> dict | None:
    """Nearest SEPA gauge whose 15-min Precip series reported in the last 24h.

    `gauges` is fetch_sepa_precip_stations() output (fetched once, ~380 rows).
    ts_id is resolved here so the collector needs one batched values call, no lookups.
    """
    with_pos = [g for g in gauges if g.get("station_latitude") and g.get("station_longitude")]
    with_pos.sort(key=lambda g: haversine_km(
        lat, lon, float(g["station_latitude"]), float(g["station_longitude"])))
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    for g in with_pos[:4]:
        meta = fetch_sepa_ts_meta(g["station_no"])
        time.sleep(0.2)
        if not meta or not meta.get("to"):
            continue
        if datetime.fromisoformat(meta["to"].replace("Z", "+00:00")) > cutoff:
            glat, glon = float(g["station_latitude"]), float(g["station_longitude"])
            return {
                "station_no": g["station_no"],
                "name": g["station_name"],
                "ts_id": meta["ts_id"],
                "lat": round(glat, 6),
                "lon": round(glon, 6),
                "distance_km": round(haversine_km(lat, lon, glat, glon), 1),
            }
    return None


def pick_nrw_gauge(lat: float, lon: float, nrw_stations: list[dict]) -> dict | None:
    """Nearest NRW gauge whose Rainfall parameter reported in the last 24h (Wales).

    `nrw_stations` is fetch_nrw_stations() output — latestTime is right there, so
    liveness costs no extra calls. Rainfall parameter IDs are PER-STATION; stored in
    the registry so the collector can query without a lookup.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    live = []
    for s in nrw_stations:
        rain = next((p for p in s.get("parameters", [])
                     if p.get("paramNameEN") == "Rainfall"), None)
        if (not rain or not rain.get("latestTime")
                or s.get("latitude") is None or s.get("longitude") is None):
            continue
        if datetime.fromisoformat(rain["latestTime"].replace("Z", "+00:00")) <= cutoff:
            continue  # statusEN lies ("Online" on gauges dead since 2023) — trust latestTime
        live.append((haversine_km(lat, lon, s["latitude"], s["longitude"]), s, rain))
    if not live:
        return None
    dist, s, rain = min(live, key=lambda t: t[0])
    return {
        "station_id": s["stationId"],
        "name": s["nameEN"],
        "parameter": rain["parameter"],
        "lat": round(s["latitude"], 6),
        "lon": round(s["longitude"], 6),
        "distance_km": round(dist, 1),
    }


def main() -> None:
    # 1. Discover + dedupe Met Office stations
    stations: dict[str, dict] = {}
    for city, lat, lon in SEED_CITIES:
        meta = fetch_nearest_land_station(lat, lon)
        time.sleep(0.2)
        if not meta or "geohash" not in meta:
            print(f"  {city}: no station found")
            continue
        gh = meta["geohash"]
        if gh in stations:
            print(f"  {city}: duplicate of {stations[gh]['seed_city']} ({gh})")
            continue
        st_lat, st_lon = geohash_decode(gh)
        stations[gh] = {
            "id": gh, "seed_city": city,
            "lat": round(st_lat, 4), "lon": round(st_lon, 4),
            "area": meta.get("area"), "region": meta.get("region"),
            "country": meta.get("country"),
        }
    print(f"discovered {len(stations)} unique stations from {len(SEED_CITIES)} seeds")

    # 2. Health check: >=40/48 entries with temperature
    obs = fetch_land_obs(list(stations))
    healthy = {}
    for gh, station in stations.items():
        entries = obs.get(gh) or []
        n_temp = sum(1 for e in entries if isinstance(e, dict) and e.get("temperature") is not None)
        if n_temp >= 40:
            healthy[gh] = station
        else:
            print(f"  DROP {station['seed_city']} ({gh}): only {n_temp}/48 temperature entries")
    print(f"{len(healthy)} stations pass health check")

    # 3. Pair EA gauge (England) + SEPA gauge (Scotland) + NRW gauge (Wales) + METAR
    live_metars = {m.get("icaoId") for m in fetch_metar([a[0] for a in METAR_AIRPORTS], hours=3)}
    sepa_gauges = fetch_sepa_precip_stations()
    nrw_stations = fetch_nrw_stations()
    for gh, station in healthy.items():
        station["ea_gauge"] = pick_live_gauge(station["lat"], station["lon"])
        station["sepa_gauge"] = (
            pick_sepa_gauge(station["lat"], station["lon"], sepa_gauges)
            if station.get("country") == "Scotland" else None
        )
        station["nrw_gauge"] = (
            pick_nrw_gauge(station["lat"], station["lon"], nrw_stations)
            if station.get("country") == "Wales" else None
        )
        icao, dist = min(
            ((a, haversine_km(station["lat"], station["lon"], alat, alon))
             for a, alat, alon in METAR_AIRPORTS),
            key=lambda t: t[1],
        )
        station["metar"] = (
            {"icao": icao, "distance_km": round(dist, 1)} if dist <= 40 and icao in live_metars else None
        )
        gauge = station["ea_gauge"]
        sepa = station["sepa_gauge"]
        nrw = station["nrw_gauge"]
        print(f"  {station['seed_city']:<14} gauge={'%s @%skm' % (gauge['station_reference'], gauge['distance_km']) if gauge else '-':<22} "
              f"sepa={'%s @%skm' % (sepa['name'], sepa['distance_km']) if sepa else '-':<28} "
              f"nrw={'%s @%skm' % (nrw['name'], nrw['distance_km']) if nrw else '-':<28} "
              f"metar={station['metar']['icao'] if station['metar'] else '-'}")

    STATIONS_FILE.parent.mkdir(exist_ok=True)
    STATIONS_FILE.write_text(json.dumps({
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "notes": "Fixed verification locations. Do not move stations casually - continuity matters.",
        "stations": sorted(healthy.values(), key=lambda s: s["seed_city"]),
    }, indent=1))
    print(f"\nwrote {STATIONS_FILE} with {len(healthy)} stations")


if __name__ == "__main__":
    main()
