"""Normalisation layer: raw + backfill JSON -> tidy Parquet under data/norm/.

Full rebuild each run (idempotent; minutes at current volumes). Two tables:

forecasts.parquet
    source      'prev_runs' | 'ukmo_forecast' | 'ukmo_ensemble'
    model       'ukmo_seamless' | 'ukmo_global_ensemble_20km'
    station_id  geohash from data/stations.json
    init_time   UTC. prev_runs: valid_time - lead (approx, daily granularity).
                live sources: the collector fetch time (init is not in the payload;
                lead is therefore approximate at the 6 h collection cadence).
    valid_time  UTC, hourly
    lead_hours  int; live rows with negative lead (past hours in the payload) dropped
    variable    controlled vocab, see below
    value       float
    member      ensemble member (0 = control), null for deterministic

observations.parquet
    source      'era5' | 'land_obs' | 'ea_rain' | 'metar'
    station_id, valid_time, variable, value as above

Variable vocabulary and units — ALL unit conversion happens here:
    temp_c        deg C.  Open-Meteo/ERA5 native; land_obs native (0.01 C resolution);
                  METAR integer C.
    precip_mm     mm accumulated over the hour PRECEDING valid_time (Open-Meteo
                  convention). EA 15-min readings are summed into that window; an hour
                  needs all four 15-min slices to count. QC: negative readings clamped
                  to 0, single readings > 20 mm/15min discarded as absurd.
    wind_ms       m/s. Open-Meteo/ERA5 km/h / 3.6; METAR knots * 0.514444;
                  land_obs already m/s (verified empirically 2026-07-05 against
                  co-located METAR at 8 airports - values match kt->m/s conversion).
    gust_ms       m/s, same conversions as wind_ms.
    rain_occurred 0/1. era5/ea_rain: hourly precip_mm >= 0.1. land_obs: Met Office
                  significant-weather code in the liquid-precip set {9..18, 28..30}
                  (rain/drizzle/sleet/thunder; hail+snow excluded). metar: wxString
                  contains RA or DZ - instantaneous at obs time, not an hourly
                  accumulation; treat as "raining around the top of the hour".

METAR reports ~2/h; the report closest to each top-of-hour (within +/-30 min) is kept.
Overlapping windows across collections deduped keep-last (later file wins).

Run: uv run python -m wpq.normalize
"""

import gzip
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl

from wpq.config import DATA_DIR
from wpq.collect import load_stations

NORM_DIR = DATA_DIR / "norm"
BACKFILL_CHUNK_SIZE = 11  # must match scripts/backfill_ukmo.py
RAIN_THRESHOLD_MM = 0.1
EA_MAX_MM_PER_15MIN = 20.0
LAND_OBS_RAIN_CODES = frozenset(range(9, 19)) | frozenset(range(28, 31))
KT_TO_MS = 0.514444

# Open-Meteo variable -> (vocab name, multiplier to normalised units)
OM_VARS = {
    "temperature_2m": ("temp_c", 1.0),
    "precipitation": ("precip_mm", 1.0),
    "wind_speed_10m": ("wind_ms", 1 / 3.6),
    "wind_gusts_10m": ("gust_ms", 1 / 3.6),
}
ENSEMBLE_KEY_RE = re.compile(r"^(.+?)(?:_member(\d+))?_ukmo_global_ensemble_20km$")

FCST_SCHEMA = {
    "source": pl.Utf8, "model": pl.Utf8, "station_id": pl.Utf8,
    "init_time": pl.Datetime("us"), "valid_time": pl.Datetime("us"),
    "lead_hours": pl.Int32, "variable": pl.Utf8, "value": pl.Float64,
    "member": pl.Int32,
}
OBS_SCHEMA = {
    "source": pl.Utf8, "station_id": pl.Utf8, "valid_time": pl.Datetime("us"),
    "variable": pl.Utf8, "value": pl.Float64,
}


def read_gz(path: Path):
    return json.loads(gzip.decompress(path.read_bytes()))


def parse_times(hourly: dict) -> list[datetime]:
    return [datetime.fromisoformat(t) for t in hourly["time"]]


def fetch_time(path: Path) -> datetime:
    """data/raw/{source}/YYYY-MM-DD/HHMMZ.json.gz -> UTC datetime."""
    return datetime.strptime(f"{path.parent.name}T{path.stem.split('.')[0]}",
                             "%Y-%m-%dT%H%MZ")


class Rows:
    """Columnar accumulator -> polars DataFrame (dodges 10M+ per-row tuples)."""

    def __init__(self, schema: dict):
        self.schema = schema
        self.cols = {k: [] for k in schema}

    def add(self, **kw):
        for k, col in self.cols.items():
            col.append(kw.get(k))

    def extend(self, n: int, consts: dict, **seqs):
        for k, col in self.cols.items():
            col.extend(seqs[k] if k in seqs else [consts.get(k)] * n)

    def frame(self) -> pl.DataFrame:
        return pl.DataFrame(self.cols, schema=self.schema)


# --------------------------------------------------------------------------- forecasts

def backfill_chunks(source: str, stations: list[dict]):
    """Yield (station, hourly dict) joined by position within each chunk file."""
    for path in sorted((DATA_DIR / "backfill" / source).glob("*.json.gz")):
        ci = int(path.stem.split("_c")[-1].split(".")[0])
        chunk = stations[ci * BACKFILL_CHUNK_SIZE:(ci + 1) * BACKFILL_CHUNK_SIZE]
        payload = read_gz(path)
        locations = payload if isinstance(payload, list) else [payload]
        for station, loc in zip(chunk, locations):
            yield station, loc.get("hourly", {})


def load_prev_runs(stations: list[dict]) -> pl.DataFrame:
    rows = Rows(FCST_SCHEMA)
    for station, hourly in backfill_chunks("prev_runs", stations):
        if not hourly.get("time"):
            continue
        times = parse_times(hourly)
        for om_var, (var, mult) in OM_VARS.items():
            for day in range(6):
                # day-0 forecasts come back under the plain variable name
                key = om_var if day == 0 else f"{om_var}_previous_day{day}"
                vals = hourly.get(key)
                if not vals:
                    continue
                lead = timedelta(days=day)
                pairs = [(t, v) for t, v in zip(times, vals) if v is not None]
                rows.extend(
                    len(pairs),
                    {"source": "prev_runs", "model": "ukmo_seamless",
                     "station_id": station["id"], "lead_hours": day * 24,
                     "variable": var, "member": None},
                    valid_time=[t for t, _ in pairs],
                    init_time=[t - lead for t, _ in pairs],
                    value=[v * mult for _, v in pairs],
                )
    return rows.frame()


def load_live_forecast(stations: list[dict]) -> pl.DataFrame:
    rows = Rows(FCST_SCHEMA)
    for path in sorted((DATA_DIR / "raw" / "ukmo_forecast").glob("*/*.json.gz")):
        fetched = fetch_time(path)
        for station, loc in zip(stations, read_gz(path)):
            hourly = loc.get("hourly", {})
            if not hourly.get("time"):
                continue
            times = parse_times(hourly)
            leads = [round((t - fetched).total_seconds() / 3600) for t in times]
            for om_var, (var, mult) in OM_VARS.items():
                vals = hourly.get(om_var)
                if not vals:
                    continue
                trip = [(t, l, v) for t, l, v in zip(times, leads, vals)
                        if v is not None and l >= 0]
                rows.extend(
                    len(trip),
                    {"source": "ukmo_forecast", "model": "ukmo_seamless",
                     "station_id": station["id"], "init_time": fetched,
                     "variable": var, "member": None},
                    valid_time=[t for t, _, _ in trip],
                    lead_hours=[l for _, l, _ in trip],
                    value=[v * mult for _, _, v in trip],
                )
    return rows.frame()


def load_live_ensemble(stations: list[dict]) -> pl.DataFrame:
    rows = Rows(FCST_SCHEMA)
    for path in sorted((DATA_DIR / "raw" / "ukmo_ensemble").glob("*/*.json.gz")):
        fetched = fetch_time(path)
        for station, loc in zip(stations, read_gz(path)):
            hourly = loc.get("hourly", {})
            if not hourly.get("time"):
                continue
            times = parse_times(hourly)
            leads = [round((t - fetched).total_seconds() / 3600) for t in times]
            for key, vals in hourly.items():
                m = ENSEMBLE_KEY_RE.match(key)
                if not m or m.group(1) not in OM_VARS or not vals:
                    continue
                var, mult = OM_VARS[m.group(1)]
                member = int(m.group(2)) if m.group(2) else 0  # plain key = control
                trip = [(t, l, v) for t, l, v in zip(times, leads, vals)
                        if v is not None and l >= 0]
                rows.extend(
                    len(trip),
                    {"source": "ukmo_ensemble", "model": "ukmo_global_ensemble_20km",
                     "station_id": station["id"], "init_time": fetched,
                     "variable": var, "member": member},
                    valid_time=[t for t, _, _ in trip],
                    lead_hours=[l for _, l, _ in trip],
                    value=[v * mult for _, _, v in trip],
                )
    return rows.frame()


# ------------------------------------------------------------------------ observations

def load_era5(stations: list[dict]) -> pl.DataFrame:
    rows = Rows(OBS_SCHEMA)
    for station, hourly in backfill_chunks("era5", stations):
        if not hourly.get("time"):
            continue
        times = parse_times(hourly)
        for om_var, (var, mult) in OM_VARS.items():
            vals = hourly.get(om_var)
            if not vals:
                continue
            pairs = [(t, v) for t, v in zip(times, vals) if v is not None]
            rows.extend(
                len(pairs),
                {"source": "era5", "station_id": station["id"], "variable": var},
                valid_time=[t for t, _ in pairs],
                value=[v * mult for _, v in pairs],
            )
            if om_var == "precipitation":
                rows.extend(
                    len(pairs),
                    {"source": "era5", "station_id": station["id"],
                     "variable": "rain_occurred"},
                    valid_time=[t for t, _ in pairs],
                    value=[float(v >= RAIN_THRESHOLD_MM) for _, v in pairs],
                )
    return rows.frame()


def load_land_obs(stations: list[dict]) -> pl.DataFrame:
    station_ids = {s["id"] for s in stations}
    rows = Rows(OBS_SCHEMA)
    for path in sorted((DATA_DIR / "raw" / "land_obs").glob("*/*.json.gz")):
        for sid, entries in read_gz(path).items():
            if sid not in station_ids or not entries:
                continue
            for e in entries:
                if not e.get("datetime"):
                    continue
                t = datetime.fromisoformat(e["datetime"].replace("Z", ""))
                for field, var, mult in (("temperature", "temp_c", 1.0),
                                         ("wind_speed", "wind_ms", 1.0),
                                         ("wind_gust", "gust_ms", 1.0)):
                    if e.get(field) is not None:
                        rows.add(source="land_obs", station_id=sid, valid_time=t,
                                 variable=var, value=e[field] * mult)
                if e.get("weather_code") is not None:
                    rows.add(source="land_obs", station_id=sid, valid_time=t,
                             variable="rain_occurred",
                             value=float(e["weather_code"] in LAND_OBS_RAIN_CODES))
    # overlapping 48 h windows across collections: later file wins
    return rows.frame().unique(subset=["station_id", "valid_time", "variable"],
                               keep="last", maintain_order=True)


def load_ea_rain(stations: list[dict]) -> pl.DataFrame:
    ref_to_sid = {s["ea_gauge"]["station_reference"]: s["id"]
                  for s in stations if s.get("ea_gauge")}
    readings: dict[tuple[str, datetime], float | None] = {}
    for path in sorted((DATA_DIR / "raw" / "ea_rain").glob("*/*.json.gz")):
        for ref, obj in read_gz(path).items():
            sid = ref_to_sid.get(ref)
            if sid is None or not obj:
                continue
            for item in obj.get("items", []):
                v = item.get("value")
                if v is None or not isinstance(v, (int, float)):
                    continue
                v = max(float(v), 0.0)  # tipping buckets report spurious negatives
                if v > EA_MAX_MM_PER_15MIN:
                    continue
                t = datetime.fromisoformat(item["dateTime"].replace("Z", ""))
                readings[(sid, t)] = v  # keep-last across overlapping fetches
    # hour ending H covers readings at H-45, H-30, H-15, H+0; need all four slices
    hours: dict[tuple[str, datetime], list[float]] = {}
    for (sid, t), v in readings.items():
        bucket = (t.replace(minute=0) + timedelta(hours=1)) if t.minute else t
        hours.setdefault((sid, bucket), []).append(v)
    rows = Rows(OBS_SCHEMA)
    for (sid, hour), vals in hours.items():
        if len(vals) != 4:
            continue
        mm = sum(vals)
        rows.add(source="ea_rain", station_id=sid, valid_time=hour,
                 variable="precip_mm", value=mm)
        rows.add(source="ea_rain", station_id=sid, valid_time=hour,
                 variable="rain_occurred", value=float(mm >= RAIN_THRESHOLD_MM))
    return rows.frame()


def load_metar(stations: list[dict]) -> pl.DataFrame:
    icao_to_sids: dict[str, list[str]] = {}
    for s in stations:
        if s.get("metar"):
            icao_to_sids.setdefault(s["metar"]["icao"], []).append(s["id"])
    # (sid, hour) -> (|offset from hour|, obs); closest report wins, later file on ties
    best: dict[tuple[str, datetime], tuple[float, dict]] = {}
    for path in sorted((DATA_DIR / "raw" / "metar").glob("*/*.json.gz")):
        for ob in read_gz(path):
            sids = icao_to_sids.get(ob.get("icaoId"))
            if not sids or not ob.get("reportTime"):
                continue
            t = datetime.fromisoformat(ob["reportTime"].replace(".000Z", ""))
            hour = t.replace(minute=0, second=0) + timedelta(
                hours=1 if t.minute >= 30 else 0)
            delta = abs((t - hour).total_seconds())
            for sid in sids:
                if delta <= best.get((sid, hour), (1801.0,))[0]:
                    best[(sid, hour)] = (delta, ob)
    rows = Rows(OBS_SCHEMA)
    for (sid, hour), (_, ob) in best.items():
        if ob.get("temp") is not None:
            rows.add(source="metar", station_id=sid, valid_time=hour,
                     variable="temp_c", value=float(ob["temp"]))
        if ob.get("wspd") is not None:
            rows.add(source="metar", station_id=sid, valid_time=hour,
                     variable="wind_ms", value=ob["wspd"] * KT_TO_MS)
        if ob.get("wgst") is not None:
            rows.add(source="metar", station_id=sid, valid_time=hour,
                     variable="gust_ms", value=ob["wgst"] * KT_TO_MS)
        wx = ob.get("wxString") or ""
        rows.add(source="metar", station_id=sid, valid_time=hour,
                 variable="rain_occurred",
                 value=float("RA" in wx or "DZ" in wx))
    return rows.frame()


# ------------------------------------------------------------------------------- main

def main() -> None:
    stations = load_stations()
    NORM_DIR.mkdir(parents=True, exist_ok=True)

    forecasts = pl.concat([
        load_prev_runs(stations),
        load_live_forecast(stations),
        load_live_ensemble(stations),
    ]).sort(["source", "model", "station_id", "variable", "valid_time", "lead_hours"])
    forecasts.write_parquet(NORM_DIR / "forecasts.parquet", compression="zstd")

    observations = pl.concat([
        load_era5(stations),
        load_land_obs(stations),
        load_ea_rain(stations),
        load_metar(stations),
    ]).sort(["source", "station_id", "variable", "valid_time"])
    observations.write_parquet(NORM_DIR / "observations.parquet", compression="zstd")

    for name, df in (("forecasts", forecasts), ("observations", observations)):
        by_src = df.group_by("source").len().sort("source")
        counts = ", ".join(f"{s}={n:,}" for s, n in by_src.iter_rows())
        print(f"{name}: {df.height:,} rows ({counts}) "
              f"-> data/norm/{name}.parquet")


if __name__ == "__main__":
    main()
