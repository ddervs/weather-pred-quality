"""Configuration: env vars (from .env locally, real env in CI) and shared constants."""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"
STATIONS_FILE = DATA_DIR / "stations.json"

USER_AGENT = (
    "weather-pred-quality/0.1 (forecast verification research; "
    "https://github.com/ddervs/weather-pred-quality; ddervs@googlemail.com)"
)


def get_env(name: str) -> str:
    """Env var, falling back to .env at the repo root (never logged)."""
    if name in os.environ:
        return os.environ[name]
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip("'\"")
    raise KeyError(f"{name} not set in environment or .env")
