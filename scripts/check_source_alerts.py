"""Hard-red alert: open (and instantly close) a GitHub issue when a collector
source has produced no raw file for 24h+ (i.e. every run failed for a day).

Runs after every collect (collect.yml, if: always()). Staleness is read from
data/raw file paths - a failed fetch writes no file - so the check is stateless.
Dedup: a source already named in a `source-alert` issue from the last 7 days is
not re-alerted; the Monday weekly report is the persistent record. The issue
@-mentions $OWNER so GitHub emails it (scotbet pattern), then closes it.

Without GH_TOKEN this is a dry run: it prints what it would do and exits 0.
It never exits non-zero - alerting must not change the collect job's status.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wpq.config import DATA_DIR

# 6-hourly sources: >26h = 4+ consecutive failures (2h slack for cron jitter).
# Ensembles run 2/day: >38h = 3+ missed slots.
STALE_HOURS_DEFAULT = 26
STALE_HOURS = {"ukmo_ensemble": 38}
SOURCES = ["ukmo_forecast", "ukmo_ensemble", "land_obs", "ea_rain",
           "sepa_rain", "nrw_rain", "metar"]
DEDUP_DAYS = 7
LABEL = "source-alert"


def latest_run(source: str) -> datetime | None:
    files = sorted((DATA_DIR / "raw" / source).glob("*/*.json.gz"))
    for f in reversed(files):
        try:
            stamp = f.parent.name + f.name.removesuffix(".json.gz")
            return datetime.strptime(stamp, "%Y-%m-%d%H%MZ")
        except ValueError:
            continue
    return None


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True,
                          text=True).stdout


def recently_alerted() -> set[str]:
    """Sources named in a source-alert issue title within the dedup window."""
    out = gh("issue", "list", "--label", LABEL, "--state", "all",
             "--limit", "50", "--json", "title,createdAt")
    cutoff = datetime.now(timezone.utc) - timedelta(days=DEDUP_DAYS)
    hit = set()
    for issue in json.loads(out):
        created = datetime.fromisoformat(issue["createdAt"].replace("Z", "+00:00"))
        if created >= cutoff:
            hit |= {s for s in SOURCES if s in issue["title"]}
    return hit


def main() -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    stale = []
    for source in SOURCES:
        last = latest_run(source)
        limit = STALE_HOURS.get(source, STALE_HOURS_DEFAULT)
        age = (now - last).total_seconds() / 3600 if last else float("inf")
        if age > limit:
            stale.append((source, last, age))
    if not stale:
        print(f"all {len(SOURCES)} sources fresh")
        return

    for source, last, age in stale:
        when = f"{last:%Y-%m-%d %H:%M}Z" if last else "never"
        print(f"STALE {source}: last successful run {when} ({age:.0f}h ago)")

    if not os.environ.get("GH_TOKEN"):
        print("GH_TOKEN not set - dry run, no issue created")
        return
    try:
        already = recently_alerted()
        fresh = [s for s in stale if s[0] not in already]
        if not fresh:
            print(f"already alerted within {DEDUP_DAYS} days - skipping")
            return
        names = ", ".join(s for s, _, _ in fresh)
        lines = [f"Every collect run has failed for 24h+ on: **{names}**.", "",
                 "| Source | Last successful run | Stale for |", "|--|--|--|"]
        for source, last, age in fresh:
            when = f"{last:%Y-%m-%d %H:%M}Z" if last else "never"
            lines += [f"| `{source}` | {when} | {age:.0f} h |"]
        lines += ["", "Check the [collect runs](../actions/workflows/collect.yml) "
                  "for the failing step's error. One alert per source per "
                  f"{DEDUP_DAYS} days; the weekly report tracks it from here.",
                  "", f"_cc @{os.environ.get('OWNER', 'ddervs')}_"]
        subprocess.run(["gh", "label", "create", LABEL, "--description",
                        "Collector source down 24h+", "--color", "d93f0b"],
                       capture_output=True)
        url = gh("issue", "create", "--title", f"Source alert: {names}",
                 "--label", LABEL, "--body", "\n".join(lines)).strip()
        print(f"created {url}")
        gh("issue", "close", url, "--reason", "completed")
    except subprocess.CalledProcessError as exc:
        print(f"alerting failed (non-fatal): {exc.stderr or exc}")


if __name__ == "__main__":
    main()
