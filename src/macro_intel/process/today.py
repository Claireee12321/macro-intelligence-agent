"""'Today' block for the top of the overview and briefing (deterministic).

Order (owner, 2026-11-05): 1) central-bank decisions/meetings in the last 24 h or later today,
2) key official data releases in the last 24 h, 3) US stock market (see process/equities.py).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from macro_intel.process.calendar import FAMILY_NAMES
from macro_intel.process.classify import families
from macro_intel.process.scoring import display_ok
from macro_intel.store import State
from macro_intel.timeutil import ET, to_utc, utc_now

CB_FAMILIES = {"fed": "Federal Reserve", "ecb": "ECB", "boe": "Bank of England", "boj": "Bank of Japan",
               "pboc": "People's Bank of China", "boc": "Bank of Canada", "rba": "Reserve Bank of Australia",
               "rbnz": "Reserve Bank of New Zealand", "snb": "Swiss National Bank"}
_DECISION_HINT = ("rate", "decision", "statement", "policy", "votes", "summary")


def policy_decisions(state: State, back_hours: int = 24) -> list[dict[str, Any]]:
    now = utc_now()
    lo = now - timedelta(hours=back_hours)
    today_end = now.astimezone(ET).replace(hour=23, minute=59)
    groups: dict[tuple, list] = {}
    for c in state.calendar.values():
        if c.family not in CB_FAMILIES or not c.scheduled_at or c.importance != "high":
            continue
        if not (lo <= c.scheduled_at <= today_end):
            continue
        if not any(h in c.title.lower() for h in _DECISION_HINT) and "fomc" not in c.title.lower():
            continue
        groups.setdefault((c.family, c.date.isoformat()), []).append(c)
    out = []
    for (fam, d), rows in groups.items():
        rows.sort(key=lambda c: c.scheduled_at)
        when = rows[0].scheduled_at
        lines = [{"title": c.title, "consensus": c.consensus, "consensus_source": c.consensus_source,
                  "previous": c.previous, "actual": c.actual, "actual_source": c.actual_source} for c in rows]
        outcome = None
        for c in rows:
            if c.release_id and c.release_id in state.releases:
                r = state.releases[c.release_id]
                outcome = {"text": (r.notes[0] if r.notes else f"{r.short}: {r.actual}"), "source": r.source_name,
                           "release_id": r.id}
        # Latest attributed coverage of this central bank around the meeting.
        cover = None
        for ev in sorted(state.events.values(), key=lambda e: -e.importance):
            if fam in families(ev.concepts) and display_ok(ev) and ev.last_published_at and \
                    abs((to_utc(ev.last_published_at) - when).total_seconds()) <= 18 * 3600:
                cover = {"event_id": ev.id, "title": ev.title, "sources": len(ev.source_ids)}
                break
        out.append({
            "family": fam, "bank": CB_FAMILIES[fam], "name": FAMILY_NAMES.get(fam, CB_FAMILIES[fam]),
            "date": d, "scheduled_at": when.isoformat(), "status": "done" if when <= now else "later today",
            "lines": lines, "outcome": outcome, "coverage": cover,
        })
    out.sort(key=lambda x: x["scheduled_at"])
    return out


def key_releases(state: State, back_hours: int = 24) -> list:
    cut = utc_now() - timedelta(hours=back_hours)
    rels = [r for r in state.releases.values() if to_utc(r.release_time or r.detected_at) >= cut]
    return sorted(rels, key=lambda r: (r.importance != "high", to_utc(r.release_time or r.detected_at)))
