"""JSON-file state store (system of record).

Each collection is one JSON file under ``<data_dir>/state/``. Writes are atomic
(temp file + rename). The ``State`` dataclass is the in-memory view; ``Store`` loads and
saves it. Swapping to SQLite/Postgres later only requires a new Store implementation.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from macro_intel.models import (
    CalendarEvent,
    DailyBriefing,
    EconomicRelease,
    LLMCall,
    MacroEvent,
    MacroState,
    MarketSnapshot,
    NewsItem,
    RunRecord,
    SeriesData,
)
from macro_intel.timeutil import to_utc, utc_now

log = logging.getLogger("macro_intel")

SCHEMA_VERSION = 1

# Retention windows (days)
ITEM_RETENTION_DAYS = 14
EVENT_RETENTION_DAYS = 30
CALENDAR_PAST_DAYS = 45
RELEASE_RETENTION_DAYS = 400
BRIEFING_RETENTION_DAYS = 90
SNAPSHOT_KEEP = 15
RUN_KEEP = 300
LLM_CALL_RETENTION_DAYS = 60


@dataclass
class State:
    items: dict[str, NewsItem] = field(default_factory=dict)
    events: dict[str, MacroEvent] = field(default_factory=dict)
    calendar: dict[str, CalendarEvent] = field(default_factory=dict)
    releases: dict[str, EconomicRelease] = field(default_factory=dict)
    series: dict[str, SeriesData] = field(default_factory=dict)
    snapshots: list[MarketSnapshot] = field(default_factory=list)
    macro_state: MacroState | None = None
    briefings: dict[str, DailyBriefing] = field(default_factory=dict)
    llm_calls: list[LLMCall] = field(default_factory=list)
    runs: list[RunRecord] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def latest_snapshot(self) -> MarketSnapshot | None:
        return self.snapshots[-1] if self.snapshots else None


_COLLECTIONS: dict[str, tuple[str, Any]] = {
    "items": ("news_items.json", TypeAdapter(dict[str, NewsItem])),
    "events": ("events.json", TypeAdapter(dict[str, MacroEvent])),
    "calendar": ("calendar.json", TypeAdapter(dict[str, CalendarEvent])),
    "releases": ("releases.json", TypeAdapter(dict[str, EconomicRelease])),
    "series": ("series.json", TypeAdapter(dict[str, SeriesData])),
    "snapshots": ("market_snapshots.json", TypeAdapter(list[MarketSnapshot])),
    "macro_state": ("macro_state.json", TypeAdapter(MacroState | None)),
    "briefings": ("briefings.json", TypeAdapter(dict[str, DailyBriefing])),
    "llm_calls": ("llm_calls.json", TypeAdapter(list[LLMCall])),
    "runs": ("runs.json", TypeAdapter(list[RunRecord])),
    "meta": ("meta.json", TypeAdapter(dict[str, Any])),
}


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1, sort_keys=False, default=str)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


class Store:
    def __init__(self, state_dir: Path):
        self.state_dir = Path(state_dir)

    def load(self) -> State:
        state = State()
        for attr, (fname, adapter) in _COLLECTIONS.items():
            path = self.state_dir / fname
            if not path.exists():
                continue
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                setattr(state, attr, adapter.validate_python(raw))
            except Exception as exc:  # corrupted/incompatible file: keep going, but loudly
                log.error("State file %s could not be loaded (%s); starting that collection empty", path, exc)
        return state

    def save(self, state: State) -> None:
        state.meta["schema_version"] = SCHEMA_VERSION
        state.meta["saved_at"] = utc_now().isoformat()
        for attr, (fname, adapter) in _COLLECTIONS.items():
            payload = adapter.dump_python(getattr(state, attr), mode="json")
            atomic_write_json(self.state_dir / fname, payload)


def prune(state: State) -> dict[str, int]:
    """Drop data outside retention windows. Returns counts removed per collection."""
    now = utc_now()
    removed: dict[str, int] = {}

    def _drop(d: dict, keep) -> int:
        dead = [k for k, v in d.items() if not keep(v)]
        for k in dead:
            del d[k]
        return len(dead)

    item_cut = now - timedelta(days=ITEM_RETENTION_DAYS)
    removed["items"] = _drop(state.items, lambda i: to_utc(i.published_at or i.collected_at) >= item_cut)

    ev_cut = now - timedelta(days=EVENT_RETENTION_DAYS)
    removed["events"] = _drop(state.events, lambda e: to_utc(e.updated_at) >= ev_cut)
    live_events = set(state.events)
    for item in state.items.values():
        if item.event_id and item.event_id not in live_events:
            item.event_id = None

    cal_cut = now.date() - timedelta(days=CALENDAR_PAST_DAYS)
    removed["calendar"] = _drop(state.calendar, lambda c: c.date >= cal_cut)

    rel_cut = now - timedelta(days=RELEASE_RETENTION_DAYS)
    removed["releases"] = _drop(state.releases, lambda r: to_utc(r.detected_at) >= rel_cut)

    brief_cut = now.date() - timedelta(days=BRIEFING_RETENTION_DAYS)
    removed["briefings"] = _drop(state.briefings, lambda b: b.date >= brief_cut)

    removed["snapshots"] = max(0, len(state.snapshots) - SNAPSHOT_KEEP)
    state.snapshots = state.snapshots[-SNAPSHOT_KEEP:]
    # Only the latest snapshot needs price history (sparklines, reactions); keep older ones compact.
    for snap in state.snapshots[:-1]:
        for q in snap.quotes.values():
            q.history = []
    removed["runs"] = max(0, len(state.runs) - RUN_KEEP)
    state.runs = state.runs[-RUN_KEEP:]

    call_cut = now - timedelta(days=LLM_CALL_RETENTION_DAYS)
    before = len(state.llm_calls)
    state.llm_calls = [c for c in state.llm_calls if to_utc(c.at) >= call_cut]
    removed["llm_calls"] = before - len(state.llm_calls)
    return removed
