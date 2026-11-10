#!/usr/bin/env python3
"""Run gate for the scheduled job (weekdays from ~10:05 ET, once per ET day).

GitHub's cron is UTC-only and unreliable (firings can be hours late or dropped), so the workflow fires
several times on weekdays; this gate lets the first firing at/after 09:55 ET through and skips the rest
once a run has succeeded that day. Manual runs always pass.

Standard library only, so the workflow can run it *before* installing anything — skipped firings stay
cheap:  python3 src/macro_intel/schedule.py --event schedule --runs data/state/runs.json
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
EARLIEST_ET = time(9, 55)


def _parse(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def succeeded(run: dict) -> bool:
    """A run counts once its state was saved without stage errors."""
    return bool(run.get("finished_at")) and bool(run.get("ok", False))


def should_run(runs: list[dict], now: datetime, event_name: str) -> tuple[bool, str]:
    if event_name != "schedule":
        return True, f"manual trigger ({event_name or 'local'})"
    et = now.astimezone(ET)
    if et.weekday() >= 5:
        return False, "weekend — no scheduled update"
    if et.time() < EARLIEST_ET:
        return False, f"{et:%H:%M} ET is before 09:55 ET (a later firing will run)"
    for r in runs:
        if r.get("trigger") == "schedule" and succeeded(r) and _parse(r["started_at"]).astimezone(ET).date() == et.date():
            return False, f"already updated today at {_parse(r['started_at']).astimezone(ET):%H:%M} ET"
    return True, f"first successful scheduled run on {et:%a %Y-%m-%d} ({et:%H:%M} ET)"


def load_runs(path: str | Path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--event", default="")
    ap.add_argument("--runs", default="data/state/runs.json")
    args = ap.parse_args()
    ok, reason = should_run(load_runs(args.runs), datetime.now(timezone.utc), args.event)
    print(f"run={'true' if ok else 'false'} — {reason}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"run={'true' if ok else 'false'}\nreason={reason}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
