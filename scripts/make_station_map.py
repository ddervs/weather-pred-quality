"""Regenerate docs/station-map.html from data/stations.json.

Self-contained page: UK coastline (data/geo/coast.json, Natural Earth 50m via
world-atlas) + station dots coloured by paired sources, hover tooltips, detail
table. Re-run whenever the station registry changes:
    uv run scripts/make_station_map.py
Optionally refresh the README screenshot (needs Chrome):
    uv run scripts/make_station_map.py --screenshot
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
TEMPLATE = Path(__file__).parent / "templates" / "station_map.html"
OUT_HTML = ROOT / "docs" / "station-map.html"
OUT_PNG = ROOT / "docs" / "station-map.png"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

WRAPPER = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body style="margin:0">
{content}
</body>
</html>
"""


def main() -> None:
    coast = json.loads((ROOT / "data" / "geo" / "coast.json").read_text())
    stations = json.loads((ROOT / "data" / "stations.json").read_text())["stations"]
    content = (
        TEMPLATE.read_text()
        .replace("__COAST__", json.dumps(coast, separators=(",", ":")))
        .replace("__STATIONS__", json.dumps(stations, separators=(",", ":")))
    )
    OUT_HTML.write_text(WRAPPER.format(content=content))
    print(f"wrote {OUT_HTML} ({OUT_HTML.stat().st_size:,} B, {len(stations)} stations)")

    if "--screenshot" in sys.argv:
        subprocess.run(
            [CHROME, "--headless", "--disable-gpu", f"--screenshot={OUT_PNG}",
             "--window-size=1140,1330", "--hide-scrollbars", f"file://{OUT_HTML}"],
            check=True, capture_output=True,
        )
        print(f"wrote {OUT_PNG} ({OUT_PNG.stat().st_size:,} B)")


if __name__ == "__main__":
    main()
