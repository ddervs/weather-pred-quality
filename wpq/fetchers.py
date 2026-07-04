"""HTTP fetchers for every source the collector and registry builder use.

All functions return parsed JSON; callers decide persistence. Be a polite client:
shared session, identifying User-Agent, small sleeps between per-station loops.
"""

import time

import requests

from wpq.config import USER_AGENT, get_env

OPEN_METEO_FORECAST = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ENSEMBLE = "https://ensemble-api.open-meteo.com/v1/ensemble"
OPEN_METEO_PREVIOUS = "https://previous-runs-api.open-meteo.com/v1/forecast"
OPEN_METEO_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
MET_OFFICE_OBS = "https://data.hub.api.metoffice.gov.uk/observation-land/1"
EA_FLOOD = "https://environment.data.gov.uk/flood-monitoring"
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


def _get_json(url: str, params: dict | None = None, headers: dict | None = None) -> dict | list:
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


def fetch_ea_readings(station_reference: str, limit: int = 120) -> dict:
    """Latest 15-min rainfall readings for one gauge (120 readings = 30h)."""
    return _get_json(
        f"{EA_FLOOD}/id/stations/{station_reference}/readings",
        {"_sorted": "", "_limit": limit, "parameter": "rainfall"},
    )


def fetch_metar(icaos: list[str], hours: int = 6) -> list:
    return _get_json(AWC_METAR, {"ids": ",".join(icaos), "format": "json", "hours": str(hours)})
