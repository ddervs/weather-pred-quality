"""One-off backfill: UKMO forecasts at lead 0-5 days (Open-Meteo Previous Runs API)
plus ERA5 reanalysis truth (Open-Meteo Archive API) for every registry station.

Coverage: 2024-01-01 .. 2026-06-30. Chunked by station group x date window; each
response is archived as gzipped JSON under data/backfill/. Idempotent: existing
chunk files are skipped, so the script can be re-run after interruption.

~45 API calls total against a 10k/day free allowance; 1s pause between calls.
Run: uv run scripts/backfill_ukmo.py
"""

import gzip
import json
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from wpq.config import DATA_DIR
from wpq.collect import load_stations
from wpq.fetchers import OPEN_METEO_ARCHIVE, OPEN_METEO_PREVIOUS, _get_json

START, END = date(2024, 1, 1), date(2026, 6, 30)
VARS = ["temperature_2m", "precipitation", "wind_speed_10m"]
LEADS = range(6)  # previous_day0..5
CHUNK_SIZE = 11   # stations per call


def simple_windows(months: int) -> list[tuple[str, str]]:
    """Inclusive [start, end] ISO date windows of ~`months` months covering START..END."""
    out = []
    start = START
    while start <= END:
        y = start.year + (start.month - 1 + months) // 12
        m = (start.month - 1 + months) % 12 + 1
        next_start = date(y, m, 1)
        end = min(END, next_start.replace(day=1))
        # end date inclusive: day before next window, or END
        end_incl = END if next_start > END else date(y, m, 1).fromordinal(next_start.toordinal() - 1)
        out.append((start.isoformat(), end_incl.isoformat()))
        start = next_start
    return out


def fetch_chunked(name: str, url: str, base_params: dict, months: int) -> None:
    stations = load_stations()
    chunks = [stations[i:i + CHUNK_SIZE] for i in range(0, len(stations), CHUNK_SIZE)]
    out_dir = DATA_DIR / "backfill" / name
    out_dir.mkdir(parents=True, exist_ok=True)
    for start, end in simple_windows(months):
        for ci, chunk in enumerate(chunks):
            path = out_dir / f"{start}_{end}_c{ci}.json.gz"
            if path.exists():
                continue
            params = {
                "latitude": ",".join(f"{s['lat']:.4f}" for s in chunk),
                "longitude": ",".join(f"{s['lon']:.4f}" for s in chunk),
                "start_date": start,
                "end_date": end,
                "timezone": "UTC",
                **base_params,
            }
            data = _get_json(url, params)
            blob = gzip.compress(json.dumps(data, separators=(",", ":")).encode())
            path.write_bytes(blob)
            print(f"  {name} {start}..{end} chunk{ci}: {len(blob):,} B")
            time.sleep(1.0)


def main() -> None:
    print("previous-runs (UKMO, leads 0-5d)...")
    hourly = [f"{v}_previous_day{d}" for v in VARS for d in LEADS]
    fetch_chunked("prev_runs", OPEN_METEO_PREVIOUS,
                  {"hourly": ",".join(hourly), "models": "ukmo_seamless"}, months=3)

    print("ERA5 truth...")
    fetch_chunked("era5", OPEN_METEO_ARCHIVE,
                  {"hourly": ",".join(VARS)}, months=6)

    total = sum(f.stat().st_size for f in (DATA_DIR / "backfill").rglob("*.json.gz"))
    print(f"backfill complete: {total / 1e6:.1f} MB gzipped")


if __name__ == "__main__":
    main()
