"""Rebuild data/metrics/metrics.parquet from data/norm/ (see wpq/metrics.py).

Run: uv run scripts/run_metrics.py [--normalize]  (--normalize rebuilds data/norm first)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from wpq import metrics, normalize

if __name__ == "__main__":
    if "--normalize" in sys.argv:
        normalize.main()
    metrics.main()
