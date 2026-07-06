"""Collector entrypoint: fetch every live source and archive gzipped raw JSON.

Writes data/raw/{source}/{YYYY-MM-DD}/{HHMM}Z.json.gz. Payloads carry their own
init/valid timestamps, so late or duplicate runs are harmless (dedup happens at
normalisation). Ensembles are fetched when the last ensemble file is >=10 h old
(~2/day, bounding repo growth). This is deliberately NOT a wall-clock-hour gate:
GitHub cron runs arrive hours late (observed 00:20 -> 04:41), so an `hour in
(0,1,12,13)` check never matched on scheduled runs and silently collected no
ensembles at all (caught by the source-down alert, 2026-07-06).

Run: uv run python -m wpq.collect          (all sources)
     uv run python -m wpq.collect --no-ensemble | --force-ensemble
"""

import gzip
import json
import sys
from datetime import datetime, timedelta, timezone

from wpq.config import DATA_DIR, STATIONS_FILE
from wpq import fetchers

ENSEMBLE_MIN_GAP_HOURS = 10


def load_stations() -> list[dict]:
    return json.loads(STATIONS_FILE.read_text())["stations"]


def raw_run_times(source: str) -> list[datetime]:
    """Successful collector runs (naive UTC), parsed from raw file paths -
    a failed fetch writes no file, so path timestamps are the success record."""
    out = []
    for f in sorted((DATA_DIR / "raw" / source).glob("*/*.json.gz")):
        try:
            stamp = f.parent.name + f.name.removesuffix(".json.gz")
            out.append(datetime.strptime(stamp, "%Y-%m-%d%H%MZ"))
        except ValueError:
            continue
    return out


def write_raw(source: str, payload, now: datetime) -> str:
    out_dir = DATA_DIR / "raw" / source / now.strftime("%Y-%m-%d")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{now.strftime('%H%M')}Z.json.gz"
    blob = gzip.compress(json.dumps(payload, separators=(",", ":")).encode())
    path.write_bytes(blob)
    return f"{source}: {len(blob):,} B -> {path.relative_to(DATA_DIR.parent)}"


def main() -> None:
    now = datetime.now(timezone.utc)
    stations = load_stations()
    if "--force-ensemble" in sys.argv:
        include_ensemble = True
    elif "--no-ensemble" in sys.argv:
        include_ensemble = False
    else:
        last = max(raw_run_times("ukmo_ensemble"), default=None)
        include_ensemble = last is None or now.replace(tzinfo=None) - last >= timedelta(
            hours=ENSEMBLE_MIN_GAP_HOURS)

    results, failures = [], []

    def step(name: str, fn):
        try:
            results.append(write_raw(name, fn(), now))
        except Exception as exc:  # one source failing must not lose the others
            failures.append(f"{name}: {type(exc).__name__}: {exc}")

    step("ukmo_forecast", lambda: fetchers.fetch_ukmo_forecast(stations))
    if include_ensemble:
        step("ukmo_ensemble", lambda: fetchers.fetch_ukmo_ensemble(stations))
    step("land_obs", lambda: fetchers.fetch_land_obs([s["id"] for s in stations]))
    step("ea_rain", lambda: {
        s["ea_gauge"]["station_reference"]: fetchers.fetch_ea_readings(s["ea_gauge"])
        for s in stations if s.get("ea_gauge")
    })
    sepa_ts_ids = [s["sepa_gauge"]["ts_id"] for s in stations if s.get("sepa_gauge")]
    if sepa_ts_ids:  # all gauges in one KiWIS call
        step("sepa_rain", lambda: fetchers.fetch_sepa_readings(sepa_ts_ids))
    nrw_gauges = [s["nrw_gauge"] for s in stations if s.get("nrw_gauge")]
    if nrw_gauges:  # one call per gauge (needs NRW_API_KEY)
        step("nrw_rain", lambda: fetchers.fetch_nrw_readings(nrw_gauges))
    step("metar", lambda: fetchers.fetch_metar(
        sorted({s["metar"]["icao"] for s in stations if s.get("metar")})
    ))

    print(f"collect @ {now.isoformat(timespec='seconds')} | {len(stations)} stations "
          f"| ensemble={'yes' if include_ensemble else 'skipped'}")
    for line in results:
        print(" ", line)
    if failures:
        print("FAILURES:")
        for line in failures:
            print(" ", line)
        sys.exit(1)


if __name__ == "__main__":
    main()
