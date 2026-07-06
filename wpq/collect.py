"""Collector entrypoint: fetch every live source and archive gzipped raw JSON.

Writes data/raw/{source}/{YYYY-MM-DD}/{HHMM}Z.json.gz. Payloads carry their own
init/valid timestamps, so late or duplicate runs are harmless (dedup happens at
normalisation). Ensembles are fetched only on the 00Z/12Z runs to bound repo growth.

Run: uv run python -m wpq.collect          (all sources)
     uv run python -m wpq.collect --no-ensemble | --force-ensemble
"""

import gzip
import json
import sys
from datetime import datetime, timezone

from wpq.config import DATA_DIR, STATIONS_FILE
from wpq import fetchers


def load_stations() -> list[dict]:
    return json.loads(STATIONS_FILE.read_text())["stations"]


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
    include_ensemble = "--force-ensemble" in sys.argv or (
        "--no-ensemble" not in sys.argv and now.hour in (0, 1, 12, 13)
    )

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
