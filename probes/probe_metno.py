"""Probe MET Norway locationforecast 2.0 ('complete' variant) for one UK location.

Checks payload size, forecast horizon, cache headers (they require honouring
Expires / If-Modified-Since), and whether probabilistic fields (percentiles,
probability_of_precipitation) are populated outside the Nordics.
Run: uv run probes/probe_metno.py
"""

import gzip
import json
from pathlib import Path

import requests

from locations import USER_AGENT


def main() -> None:
    resp = requests.get(
        "https://api.met.no/weatherapi/locationforecast/2.0/complete",
        params={"lat": "51.5072", "lon": "-0.1276"},
        headers={"User-Agent": USER_AGENT},
        timeout=60,
    )
    print(f"status={resp.status_code}")
    print(f"Expires: {resp.headers.get('Expires')}")
    print(f"Last-Modified: {resp.headers.get('Last-Modified')}")
    resp.raise_for_status()
    raw = resp.content
    data = resp.json()

    out = Path(__file__).parent / "samples" / "metno_complete_london.json"
    out.parent.mkdir(exist_ok=True)
    out.write_bytes(raw)

    gz = len(gzip.compress(raw))
    print(f"payload: {len(raw):,} bytes raw, {gz:,} bytes gzipped (1 location)")

    steps = data["properties"]["timeseries"]
    print(f"timesteps: {len(steps)}, {steps[0]['time']} .. {steps[-1]['time']}")

    # Inspect available fields in the first step and hunt for probabilistic ones
    first_details = steps[0]["data"]["instant"]["details"]
    print("\ninstant details keys:", sorted(first_details.keys()))
    next1 = steps[0]["data"].get("next_1_hours", {})
    print("next_1_hours details:", json.dumps(next1, indent=2)[:500])

    prob_keys = set()
    for step in steps:
        for block in step["data"].values():
            details = block.get("details", {}) if isinstance(block, dict) else {}
            for k in details:
                if "probability" in k or "percentile" in k:
                    prob_keys.add(k)
    print("\nprobabilistic keys found anywhere in series:", sorted(prob_keys) or "NONE")
    print(f"sample saved to {out}")


if __name__ == "__main__":
    main()
