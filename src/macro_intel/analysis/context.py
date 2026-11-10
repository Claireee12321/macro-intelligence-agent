"""Shared, deterministic context blocks for LLM packets (all values from the data layer)."""

from __future__ import annotations

from datetime import timedelta

from macro_intel.process.calendar import FAMILY_NAMES
from macro_intel.models import MacroState, MarketQuote, MarketSnapshot
from macro_intel.store import State
from macro_intel.timeutil import ET, fmt_et, utc_now


def fmt_quote(q: MarketQuote) -> str:
    if q.value is None:
        return "n/a"
    if q.units == "%":
        v = f"{q.value:.{q.decimals}f}%"
    elif q.units == "bp":
        v = f"{q.value:+.0f}bp"
    else:
        v = f"{q.value:,.{q.decimals}f}"
    if q.change is None:
        c = "change n/a"
    elif q.change_units == "bp":
        c = f"{q.change:+.0f}bp"
    elif q.change_units == "pts":
        c = f"{q.change:+.2f}pts"
    else:
        c = f"{q.change:+.2f}%"
    return f"{v} ({c} vs prior close)"


def market_lines(snap: MarketSnapshot | None, ids: list[str] | None = None) -> list[dict]:
    if snap is None:
        return []
    out = []
    for q in snap.quotes.values():
        if ids is not None and q.id not in ids:
            continue
        if q.value is None or q.group == "fx_fallback":
            continue
        out.append({"instrument": q.label, "level_and_change": fmt_quote(q), "as_of": q.as_of_label, "source": q.source,
                    **({"note": q.note} if q.note else {})})
    return out


def regime_lines(ms: MacroState | None) -> dict:
    if ms is None:
        return {}
    return {
        d.dimension: {"state": d.state, "evidence": [f"{e.indicator}: {e.display} ({e.as_of})" for e in d.evidence],
                      **({"data_gaps": d.data_gaps} if d.data_gaps else {})}
        for d in ms.dimensions
    }


def upcoming_lines(state: State, days: int = 7, limit: int = 15) -> list[dict]:
    now = utc_now()
    horizon = now.date() + timedelta(days=days)
    from macro_intel.publish.export import calendar_visible

    rows = [c for c in state.calendar.values()
            if c.status == "upcoming" and c.date <= horizon and calendar_visible(c)]
    rows.sort(key=lambda c: (c.scheduled_at or now, c.importance != "high"))
    out = []
    for c in rows[:limit]:
        item = {"when": fmt_et(c.scheduled_at) if c.scheduled_at else c.date.isoformat(), "country": c.country,
                "event": c.title, "importance": c.importance}
        if c.family:
            item["family"] = FAMILY_NAMES.get(c.family, c.family)
        item["consensus"] = f"{c.consensus} ({c.consensus_source})" if c.consensus else "not available"
        if c.previous:
            item["previous"] = c.previous
        out.append(item)
    return out


def now_line() -> str:
    n = utc_now().astimezone(ET)
    return n.strftime("%Y-%m-%d (%A) %H:%M ET")
