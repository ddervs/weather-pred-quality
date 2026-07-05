"""Rebuild data/metrics/{conformal,brier_decomposition,bootstrap_ci}.parquet
(see wpq/calibration.py). Requires data/norm/ - rebuilds it first if missing.

Run: uv run scripts/run_calibration.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from wpq import calibration, normalize
from wpq.metrics import NORM_DIR

if __name__ == "__main__":
    if not (NORM_DIR / "forecasts.parquet").exists():
        normalize.main()
    calibration.main()
