"""Smoke-test verification metrics on the backfill: does forecast skill degrade with
lead time the way it should? If yes, the whole pipeline (station registry, previous-runs
forecasts, ERA5 truth, time alignment) is wired correctly.

Not the real metrics suite - deliberately dependency-free (no pandas/scores yet).
Computes, per lead 0-5 days, over all stations x hours 2024-01..2026-06:
  temperature: MAE, bias | wind: MAE | rain>=0.1mm/h: accuracy, POD, FAR

Run: uv run scripts/smoke_metrics.py   (after scripts/backfill_ukmo.py)
"""

import gzip
import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from wpq.config import DATA_DIR
from wpq.collect import load_stations

CHUNK_SIZE = 11  # must match backfill_ukmo.py
VARS = ["temperature_2m", "precipitation", "wind_speed_10m"]
LEADS = range(6)
T0 = datetime(2024, 1, 1)
N_HOURS = int((datetime(2026, 7, 1) - T0).total_seconds() // 3600)
RAIN_MM = 0.1


def hour_index(iso: str) -> int:
    return int((datetime.fromisoformat(iso) - T0).total_seconds() // 3600)


def lead_key(var: str, day: int) -> str:
    # previous-runs API returns day0 under the plain variable name, not *_previous_day0
    return var if day == 0 else f"{var}_previous_day{day}"


def load_series(source: str, keys: list[str]) -> dict:
    """-> {station_id: {key: [value or None]*N_HOURS}}"""
    stations = load_stations()
    out = {s["id"]: {k: [None] * N_HOURS for k in keys} for s in stations}
    for path in sorted((DATA_DIR / "backfill" / source).glob("*.json.gz")):
        ci = int(path.stem.split("_c")[-1].split(".")[0])
        chunk = stations[ci * CHUNK_SIZE:(ci + 1) * CHUNK_SIZE]
        payload = json.loads(gzip.decompress(path.read_bytes()))
        locations = payload if isinstance(payload, list) else [payload]
        for pos, loc in enumerate(locations):
            if pos >= len(chunk):
                break
            sid = chunk[pos]["id"]
            hourly = loc.get("hourly", {})
            times = hourly.get("time", [])
            if not times:
                continue
            base = hour_index(times[0])
            for key in keys:
                vals = hourly.get(key)
                if not vals:
                    continue
                series = out[sid][key]
                for i, v in enumerate(vals):
                    idx = base + i
                    if v is not None and 0 <= idx < N_HOURS:
                        series[idx] = v
    return out


def main() -> None:
    fcst_keys = [lead_key(v, d) for v in VARS for d in LEADS]
    print("loading forecasts...")
    fcst = load_series("prev_runs", fcst_keys)
    print("loading ERA5 truth...")
    truth = load_series("era5", VARS)

    print(f"\n{'lead':>4} {'n_temp':>9} {'tMAE':>6} {'tBias':>6} {'wMAE':>6} "
          f"{'rain_acc':>8} {'POD':>5} {'FAR':>5}")
    for d in LEADS:
        abs_t = bias_t = n_t = 0.0
        abs_w = n_w = 0.0
        hits = misses = false_al = corr_neg = 0
        for sid in fcst:
            ft = fcst[sid][lead_key("temperature_2m", d)]
            fw = fcst[sid][lead_key("wind_speed_10m", d)]
            fp = fcst[sid][lead_key("precipitation", d)]
            tt = truth[sid]["temperature_2m"]
            tw = truth[sid]["wind_speed_10m"]
            tp = truth[sid]["precipitation"]
            for i in range(N_HOURS):
                if ft[i] is not None and tt[i] is not None:
                    err = ft[i] - tt[i]
                    abs_t += abs(err); bias_t += err; n_t += 1
                if fw[i] is not None and tw[i] is not None:
                    abs_w += abs(fw[i] - tw[i]); n_w += 1
                if fp[i] is not None and tp[i] is not None:
                    f_rain, o_rain = fp[i] >= RAIN_MM, tp[i] >= RAIN_MM
                    if f_rain and o_rain: hits += 1
                    elif f_rain: false_al += 1
                    elif o_rain: misses += 1
                    else: corr_neg += 1
        n_rain = hits + misses + false_al + corr_neg
        if n_t == 0:
            print(f"{d:>4}  no data")
            continue
        print(f"{d:>4} {int(n_t):>9} {abs_t/n_t:>6.2f} {bias_t/n_t:>+6.2f} {abs_w/n_w:>6.2f} "
              f"{(hits+corr_neg)/n_rain:>8.1%} {hits/max(hits+misses,1):>5.1%} "
              f"{false_al/max(hits+false_al,1):>5.1%}")

    print(f"\n(rows = forecast lead in days; truth = ERA5 reanalysis; {len(fcst)} stations; "
          f"rain threshold {RAIN_MM} mm/h)")
    print("expected pattern if pipeline is sound: tMAE/wMAE rise with lead, POD falls, FAR rises")


if __name__ == "__main__":
    main()
