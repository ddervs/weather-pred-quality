"""HTTP fetchers for every source the collector and registry builder use.

All functions return parsed JSON; callers decide persistence. Be a polite client:
shared session, identifying User-Agent, small sleeps between per-station loops.
"""

import time
from datetime import datetime, timedelta, timezone

import requests

from wpq.config import USER_AGENT, get_env

OPEN_METEO_FORECAST = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ENSEMBLE = "https://ensemble-api.open-meteo.com/v1/ensemble"
OPEN_METEO_PREVIOUS = "https://previous-runs-api.open-meteo.com/v1/forecast"
OPEN_METEO_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
MET_OFFICE_OBS = "https://data.hub.api.metoffice.gov.uk/observation-land/1"
EA_FLOOD = "https://environment.data.gov.uk/flood-monitoring"
SEPA_KIWIS = "https://timeseries.sepa.org.uk/KiWIS/KiWIS"
NRW_RIVERS_SEAS = "https://api.naturalresources.wales/rivers-and-seas/v1/api"
AWC_METAR = "https://aviationweather.gov/api/data/metar"

UKMO_HOURLY_VARS = [
    "temperature_2m",
    "precipitation",
    "rain",
    "snowfall",
    "wind_speed_10m",
    "wind_gusts_10m",
    "wind_direction_10m",
    "cloud_cover",
    "relative_humidity_2m",
]

ENSEMBLE_VARS = ["temperature_2m", "precipitation", "wind_speed_10m"]

_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT

# EA served 502/503/500 bursts for days (2026-07-12..15) and SEPA threw a one-off
# 429; both cleared on their own, so transient upstream trouble gets a couple of
# spaced retries before we give up and let the collector record the failure.
_RETRY_STATUSES = {429, 500, 502, 503, 504}
_RETRY_DELAYS = (5, 30)


def _get_json(url: str, params: dict | None = None, headers: dict | None = None) -> dict | list:
    for delay in _RETRY_DELAYS:
        resp = _session.get(url, params=params, headers=headers, timeout=90)
        if resp.status_code not in _RETRY_STATUSES:
            break
        time.sleep(delay)
    else:
        resp = _session.get(url, params=params, headers=headers, timeout=90)
    resp.raise_for_status()
    return resp.json()


def _coords(stations: list[dict]) -> dict:
    return {
        "latitude": ",".join(f"{s['lat']:.4f}" for s in stations),
        "longitude": ",".join(f"{s['lon']:.4f}" for s in stations),
    }


def fetch_ukmo_forecast(stations: list[dict]) -> dict | list:
    """Deterministic UKMO forecast (UKV+global blend) for all stations, one call."""
    return _get_json(OPEN_METEO_FORECAST, {
        **_coords(stations),
        "hourly": ",".join(UKMO_HOURLY_VARS),
        "models": "ukmo_seamless",
        "forecast_days": "8",
        "timezone": "UTC",
    })


def fetch_ukmo_ensemble(stations: list[dict]) -> dict | list:
    """MOGREPS ensemble members for all stations, one call. Largest payload we store."""
    return _get_json(OPEN_METEO_ENSEMBLE, {
        **_coords(stations),
        "hourly": ",".join(ENSEMBLE_VARS),
        "models": "ukmo_global_ensemble_20km,ukmo_uk_ensemble_2km",
        "forecast_days": "6",
        "timezone": "UTC",
    })


def fetch_land_obs(geohashes: list[str]) -> dict:
    """Met Office land observations, one call per station (48h hourly window each)."""
    headers = {"apikey": get_env("MET_OFFICE_LAND_OBS_API_KEY")}
    out = {}
    for gh in geohashes:
        # Some stations returned by /nearest have no obs feed (404) — record as absent
        resp = _session.get(f"{MET_OFFICE_OBS}/{gh}", headers=headers, timeout=90)
        out[gh] = resp.json() if resp.status_code == 200 else None
        time.sleep(0.2)
    return out


def fetch_nearest_land_station(lat: float, lon: float) -> dict | None:
    """Nearest land-obs station metadata. API requires <=2dp coordinates."""
    headers = {"apikey": get_env("MET_OFFICE_LAND_OBS_API_KEY")}
    data = _get_json(
        f"{MET_OFFICE_OBS}/nearest",
        {"lat": round(lat, 2), "lon": round(lon, 2)},
        headers=headers,
    )
    return data[0] if isinstance(data, list) and data else None


def fetch_ea_gauges_near(lat: float, lon: float, dist_km: int = 25) -> list[dict]:
    data = _get_json(f"{EA_FLOOD}/id/stations",
                     {"parameter": "rainfall", "lat": lat, "long": lon, "dist": dist_km})
    return data.get("items", [])


def fetch_ea_rain_measure(station_reference: str) -> dict | None:
    """Resolve which rainfall series to collect: {'measure': id-tail, 'period': s}.

    Gauges publish 1-3 rainfall measures and the obvious one is often DEAD (four
    of ours have a dormant `t-15_min` totals series while a `rainfall-water` or
    `i-15_min` twin reports fine; two are hourly-only `t-1_h`). So: walk the
    candidates in preference order (15-min totals > 15-min instantaneous > hourly
    totals) and pin the first whose latest reading is < 48 h old. None = gauge dead.
    """
    items = _get_json(f"{EA_FLOOD}/id/stations/{station_reference}/measures")["items"]
    tails = [m["@id"].split("/")[-1] for m in items if m.get("parameter") == "rainfall"]
    rank = lambda t: ("-t-15_min-" not in t, "tipping_bucket" not in t,
                      "-i-15_min-" not in t)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    for tail in sorted(tails, key=rank):
        r = _get_json(f"{EA_FLOOD}/id/measures/{tail}/readings",
                      {"_sorted": "", "_limit": 1}).get("items", [])
        if r and datetime.fromisoformat(r[0]["dateTime"].replace("Z", "+00:00")) > cutoff:
            return {"measure": tail, "period": 3600 if "-t-1_h-" in tail else 900}
        time.sleep(0.2)
    return None


def fetch_ea_readings(gauge: dict, limit: int = 120) -> dict:
    """Latest readings for one gauge's pinned measure (120 x 15 min = 30h).

    Falls back to the whole-station endpoint if the registry entry predates
    measure pinning (normalize filters by measure either way).
    """
    if gauge.get("measure"):
        return _get_json(f"{EA_FLOOD}/id/measures/{gauge['measure']}/readings",
                         {"_sorted": "", "_limit": limit})
    return _get_json(
        f"{EA_FLOOD}/id/stations/{gauge['station_reference']}/readings",
        {"_sorted": "", "_limit": limit, "parameter": "rainfall"},
    )


def _sepa(request: str, **params) -> list:
    """SEPA KiWIS query (keyless, OGL). timezone=UTC pinned; Z-suffixed timestamps."""
    return _get_json(SEPA_KIWIS, {
        "service": "kisters", "type": "queryServices", "datasource": "0",
        "format": "json", "timezone": "UTC", "request": request, **params,
    })


def fetch_sepa_precip_stations() -> list[dict]:
    """All SEPA precipitation gauges (~380, Scotland). One call."""
    rows = _sepa(
        "getStationList", parametertype_name="Precip",
        returnfields="station_name,station_no,station_id,"
                     "station_latitude,station_longitude",
    )
    return [dict(zip(rows[0], r)) for r in rows[1:]]


def fetch_sepa_ts_meta(station_no: str) -> dict | None:
    """15-min Precip series metadata (ts_id + from/to coverage) for one gauge."""
    rows = _sepa(
        "getTimeseriesList", station_no=station_no,
        ts_name="15minute.Total", parametertype_name="Precip",
        returnfields="station_no,station_name,ts_id,coverage",
    )
    return dict(zip(rows[0], rows[1])) if len(rows) > 1 else None


def fetch_sepa_readings(ts_ids: list[str], period: str = "PT30H") -> list[dict]:
    """15-min rainfall (mm) for many gauges in ONE call; metadata labels each series."""
    return _sepa(
        "getTimeseriesValues", ts_id=",".join(ts_ids), period=period,
        returnfields="Timestamp,Value", metadata="true",
        md_returnfields="station_no,station_name,ts_id,ts_unitsymbol",
    )


def fetch_nrw_stations() -> list[dict]:
    """All NRW monitoring stations (~409; ~150 carry a Rainfall parameter), one call.

    Each station's parameters[] include latestTime — the real liveness signal
    (statusEN says "Online" even for gauges dead since 2023).
    """
    headers = {"Ocp-Apim-Subscription-Key": get_env("NRW_API_KEY")}
    return _get_json(f"{NRW_RIVERS_SEAS}/StationData", headers=headers)


def fetch_nrw_readings(gauges: list[dict]) -> dict:
    """15-min rainfall (mm) per gauge, one call each, ~last 30 h.

    The historical endpoint returns a FULL YEAR (~35k readings, 1.5 MB) unless
    windowed; `from`/`to` (dates, `to` end-exclusive) are the only params it
    honours. Rainfall parameter IDs are per-station — taken from the gauge dict.
    """
    headers = {"Ocp-Apim-Subscription-Key": get_env("NRW_API_KEY")}
    now = datetime.now(timezone.utc)
    window = {"from": (now - timedelta(hours=30)).date().isoformat(),
              "to": (now + timedelta(days=1)).date().isoformat()}
    out = {}
    for g in gauges:
        out[str(g["station_id"])] = _get_json(
            f"{NRW_RIVERS_SEAS}/StationData/historical",
            {"location": g["station_id"], "parameter": g["parameter"], **window},
            headers=headers,
        )
        time.sleep(0.2)
    return out


def fetch_metar(icaos: list[str], hours: int = 6) -> list:
    return _get_json(AWC_METAR, {"ids": ",".join(icaos), "format": "json", "hours": str(hours)})
