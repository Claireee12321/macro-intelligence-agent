"""Observed market reaction around an event — measured data, never model output.

Window: the last close *before* the event → the first close *after* it (or the latest delayed
quote if that session has not closed yet; such reactions are re-measured on later runs until final).
With one update per day, attributing moves to a single event is inherently approximate; the
caveats say so explicitly.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from macro_intel.process.quotes import compute_change
from macro_intel.process.scoring import display_ok
from macro_intel.models import MacroEvent, MarketQuote, MarketSnapshot, MarketSpec, ObservedMove, ObservedReaction
from macro_intel.timeutil import ET, to_utc, utc_now

SESSION_CLOSE = time(16, 0)
MAX_EVENT_AGE = timedelta(days=4)
CAVEATS = [
    "Window moves reflect all news and flows in the period, not only this event.",
    "Intraday quotes may be delayed; each move names its source and whether it is an official close.",
]


def _measure(q: MarketQuote, spec: MarketSpec, t_event: datetime) -> tuple[ObservedMove, bool] | None:
    if not q.history or q.value is None:
        return None
    hist = [(date.fromisoformat(d), v) for d, v in q.history]
    t_et = t_event.astimezone(ET)
    d_event = t_et.date()
    in_session = t_et.weekday() < 5 and t_et.time() < SESSION_CLOSE
    start = [(d, v) for d, v in hist if (d < d_event if in_session else d <= d_event)]
    if not start:
        return None
    d0, v0 = start[-1]
    after = [(d, v) for d, v in hist if d > d0]
    if not after:
        return None
    d1, v1 = after[0]
    latest_date = hist[-1][0]
    session_done = d1 < latest_date or q.kind in ("eod", "daily_fix", "derived") or (
        q.as_of is not None and q.as_of.astimezone(ET).time() >= SESSION_CLOSE
    )
    if d1 == latest_date and not session_done:
        end_label = q.as_of_label or f"{d1.isoformat()} latest"
        v1 = q.value
    else:
        end_label = f"{d1.isoformat()} close"
    return ObservedMove(
        instrument_id=q.id, label=q.label, start_value=v0, end_value=v1,
        change=compute_change(spec, v1, v0), change_units=spec.change_units,
        start_label=f"{d0.isoformat()} close", end_label=end_label, source=q.source,
    ), session_done


def measure_reaction(event_time: datetime, snap: MarketSnapshot, specs: list[MarketSpec]) -> ObservedReaction | None:
    moves: list[ObservedMove] = []
    finals: list[bool] = []
    for spec in specs:
        if not spec.reaction or spec.id not in snap.quotes:
            continue
        res = _measure(snap.quotes[spec.id], spec, event_time)
        if res:
            mv, done = res
            moves.append(mv)
            finals.append(done)
    if not moves:
        return None
    t_et = event_time.astimezone(ET)
    return ObservedReaction(
        window=f"Last close before the event ({t_et.strftime('%Y-%m-%d %H:%M ET')}) to the next close, or latest delayed quote",
        measured_at=utc_now(), final=all(finals), moves=moves, caveats=list(CAVEATS),
    )


# Concept → calendar family whose scheduled decision time anchors the reaction window.
_POLICY_ANCHORS = {"fed_policy": "fed", "ecb_policy": "ecb", "boe_policy": "boe", "boj_policy": "boj",
                   "boc_policy": "boc", "rba_policy": "rba", "rbnz_policy": "rbnz", "snb_policy": "snb"}


def anchor_time(ev: MacroEvent, calendar) -> datetime | None:
    """Only events with an official timestamp get a reaction window: data releases (release time)
    and central-bank decisions (scheduled decision time from the calendar). Other news has no
    well-defined moment, so measuring a 'reaction' would imply causality we cannot support."""
    if ev.kind == "data_release":
        return ev.first_published_at
    fams = {_POLICY_ANCHORS[c] for c in ev.concepts if c in _POLICY_ANCHORS}
    if not fams or ev.first_published_at is None:
        return None
    lo = to_utc(ev.first_published_at) - timedelta(hours=12)
    hi = to_utc(ev.last_published_at or ev.first_published_at) + timedelta(hours=12)
    now = utc_now()
    times = [c.scheduled_at for c in calendar.values()
             if c.family in fams and c.scheduled_at and lo <= c.scheduled_at <= hi and c.scheduled_at <= now
             and c.importance == "high"]
    return min(times) if times else None


def update_reactions(events: list[MacroEvent], snap: MarketSnapshot | None, specs: list[MarketSpec],
                     min_importance: float, calendar: dict | None = None) -> int:
    if snap is None:
        return 0
    now = utc_now()
    n = 0
    for ev in events:
        if ev.importance < min_importance or not display_ok(ev) or (ev.observed_reaction and ev.observed_reaction.final):
            continue
        t = anchor_time(ev, calendar or {})
        if t is None:
            ev.observed_reaction = None
            continue
        if now - to_utc(t) > MAX_EVENT_AGE and ev.observed_reaction is None:
            continue
        r = measure_reaction(to_utc(t), snap, specs)
        if r:
            ev.observed_reaction = r
            n += 1
    return n
