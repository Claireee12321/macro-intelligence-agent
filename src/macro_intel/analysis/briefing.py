"""Stage 2: daily briefing — AI-written when a provider is enabled, deterministic otherwise.

Idempotent per (ET date, slot). Numbers in ``data_points`` always come from the data layer.
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta

from macro_intel.analysis import context
from macro_intel.analysis.llm import Budget, Provider, call_structured
from macro_intel.analysis.prompts import BRIEFING_SYSTEM
from macro_intel.config import Settings
from macro_intel.models import BriefingDraft, BriefingPoint, DailyBriefing, LLMUsage, MacroEvent
from macro_intel.process import equities, today
from macro_intel.process.indicators import fmt_value
from macro_intel.process.scoring import display_ok
from macro_intel.store import State
from macro_intel.timeutil import ET, fmt_et, fmt_release, to_utc, utc_now

log = logging.getLogger("macro_intel")

LOOKBACK = timedelta(hours=30)
MAX_EVENTS = 8


def _top_events(state: State) -> list[MacroEvent]:
    cut = utc_now() - LOOKBACK
    evs = [e for e in state.events.values()
           if display_ok(e) and to_utc(e.last_published_at or e.first_seen_at) >= cut]
    return sorted(evs, key=lambda e: -e.importance)[:MAX_EVENTS]


def _recent_releases(state: State):
    cut = utc_now() - LOOKBACK
    return sorted([r for r in state.releases.values() if to_utc(r.detected_at) >= cut], key=lambda r: r.release_time or r.detected_at)


def _release_line(r, specs) -> str:
    spec = specs.get(r.indicator_id)
    fv = (lambda v: fmt_value(v, spec)) if spec else (lambda v: f"{v:.{r.decimals}f}")
    s = f"{r.name} ({r.period_label}): {fv(r.actual)}"
    if r.consensus is not None:
        s += f" vs forecast {fv(r.consensus)} [{r.consensus_source}] — {r.surprise_direction.replace('_', ' ')}"
    else:
        s += " — consensus unavailable"
    if r.previous is not None:
        s += f"; previous {fv(r.previous)}"
    s += f" — released {fmt_release(r.release_time)}"
    return s


def _market_moves(state: State, limit: int = 6) -> list[str]:
    snap = state.latest_snapshot
    if not snap:
        return []
    scored = []
    for q in snap.quotes.values():
        if q.change is None or q.value is None or q.group == "fx_fallback":
            continue
        # Normalise: bp moves / 5, % moves / 0.5 → comparable "notability"
        scale = 5.0 if q.change_units == "bp" else (1.0 if q.change_units == "pts" else 0.5)
        scored.append((abs(q.change) / scale, q))
    scored.sort(key=lambda x: -x[0])
    return [f"{q.label}: {context.fmt_quote(q)} — {q.as_of_label}, {q.source}" for _, q in scored[:limit]]


def fmt_et_iso(iso: str) -> str:
    from datetime import datetime

    return fmt_et(datetime.fromisoformat(iso))


def deterministic_draft(state: State, settings: Settings) -> tuple[BriefingDraft, list[str]]:
    specs = {s.id: s for s in settings.indicators}
    evs = _top_events(state)
    rels = _recent_releases(state)
    ms = state.macro_state
    regime = ms.summary if ms else "Macro regime not yet assessed."
    headline = f"Data-only briefing — {regime}" if ms else "Data-only briefing"
    overview = (f"Deterministic regime assessment — {regime}. "
                f"{len(evs)} notable developments in the last {int(LOOKBACK.total_seconds() // 3600)} hours"
                + (f"; {len(rels)} new official data release(s)." if rels else "; no new official data releases.")
                + " AI interpretation is disabled, so this briefing lists facts and data only.")
    # Order: central-bank decisions, then official releases, then other top developments.
    key: list[BriefingPoint] = []
    for d in today.policy_decisions(state):
        parts = [f"{d['name']} ({d['status']}, {fmt_et_iso(d['scheduled_at'])})"]
        for ln in d["lines"][:3]:
            if ln.get("consensus") or ln.get("previous") or ln.get("actual"):
                parts.append(f"{ln['title']}: " + ", ".join(x for x in (
                    f"actual {ln['actual']}" if ln.get("actual") else "",
                    f"forecast {ln['consensus']}" if ln.get("consensus") else "",
                    f"previous {ln['previous']}" if ln.get("previous") else "") if x))
        if d.get("outcome"):
            parts.append(f"Outcome: {d['outcome']['text']} [{d['outcome']['source']}]")
        if d.get("coverage"):
            parts.append(f"Coverage: {d['coverage']['title']}")
        key.append(BriefingPoint(text=" — ".join(parts), event_ids=[d["coverage"]["event_id"]] if d.get("coverage") else []))
    for r in today.key_releases(state):
        key.append(BriefingPoint(text=_release_line(r, specs), event_ids=[r.event_id] if r.event_id else []))
    used = {x for p in key for x in p.event_ids}
    for e in evs:
        if len(key) >= 8:
            break
        if e.id not in used:
            key.append(BriefingPoint(text=f"{e.title} — importance {e.importance:.0f}, {len(e.source_ids) or 1} source(s)", event_ids=[e.id]))
    eq = equities.summarize(state)
    changed = "; ".join(_release_line(r, specs) for r in rels) if rels else "No new official data releases since the previous briefing."
    watch = [BriefingPoint(text=f"{u['when']} — {u['event']} ({u['country']}); consensus {u['consensus']}" + (f"; previous {u['previous']}" if u.get('previous') else ""))
             for u in context.upcoming_lines(state, days=7, limit=8)]
    draft = BriefingDraft(headline=headline, overview=overview, us_equity_market=eq.summary if eq else "",
                          key_developments=key, what_changed=changed, market_implications=[], what_to_watch=watch, risks=[])
    data_points = [_release_line(r, specs) for r in rels] + _market_moves(state)
    if ms:
        data_points += [f"{d.dimension.replace('_', ' ').title()}: {d.state}" for d in ms.dimensions]
    return draft, data_points


def _ai_packet(state: State, settings: Settings, evs: list[MacroEvent]) -> str:
    specs = {s.id: s for s in settings.indicators}
    events = []
    for e in evs:
        row = {"event_id": e.id, "title": e.title, "region": e.region, "topics": e.topics, "importance": e.importance,
               "first_published": fmt_et(e.first_published_at), "sources": len(e.source_ids)}
        if e.analysis:
            a = e.analysis.output
            row["prior_analysis"] = {"summary": a.summary, "narrative_effect": a.narrative_effect,
                                     "market_impacts": [m.model_dump() for m in a.market_impacts][:6]}
        if e.observed_reaction:
            row["observed_reaction"] = [{"instrument": m.label, "change": m.change, "units": m.change_units,
                                         "window": f"{m.start_label} → {m.end_label}"} for m in e.observed_reaction.moves]
        events.append(row)
    packet = {
        "now": context.now_line(),
        "events": events,
        "central_bank_decisions_last_24h_or_later_today": today.policy_decisions(state),
        "new_official_releases": [_release_line(r, specs) for r in _recent_releases(state)],
        "us_equity_market": (lambda eq: eq.model_dump(mode="json", exclude={"generated_at"}) if eq else None)(equities.summarize(state)),
        "macro_state": context.regime_lines(state.macro_state),
        "market_dashboard": context.market_lines(state.latest_snapshot),
        "upcoming_calendar": context.upcoming_lines(state, days=7),
    }
    return json.dumps(packet, ensure_ascii=False, indent=1)


def briefing_id(slot: str = "daily") -> str:
    return f"{utc_now().astimezone(ET).date().isoformat()}-{slot}"


def make_briefing(state: State, settings: Settings, provider: Provider | None, slot: str = "daily",
                  force: bool = False) -> DailyBriefing | None:
    bid = briefing_id(slot)
    existing = state.briefings.get(bid)
    if existing and not force and not (existing.mode == "data_only" and provider is not None):
        log.info("Briefing %s already exists; skipping", bid)
        return None
    draft, data_points = deterministic_draft(state, settings)
    evs = _top_events(state)
    mode, usage, model_name = "data_only", LLMUsage(), None
    if provider is not None:
        parsed, u, err = call_structured(provider, Budget(state, settings), f"briefing:{bid}", BRIEFING_SYSTEM,
                                         _ai_packet(state, settings, evs), BriefingDraft)
        if parsed is not None:
            valid = {e.id for e in evs}
            for group in (parsed.key_developments, parsed.market_implications, parsed.what_to_watch):
                for p in group:
                    p.event_ids = [x for x in p.event_ids if x in valid]
            draft, mode, usage, model_name = parsed, "ai", u or LLMUsage(), provider.model
        else:
            log.warning("AI briefing unavailable (%s); using data-only briefing", err)
    b = DailyBriefing(
        id=bid, date=utc_now().astimezone(ET).date(), slot=slot, generated_at=utc_now(), mode=mode,  # type: ignore[arg-type]
        provider=provider.name if (provider and mode == "ai") else None, model=model_name,
        content=draft, data_points=data_points, equities=equities.summarize(state), event_ids=[e.id for e in evs],
        release_ids=[r.id for r in _recent_releases(state)], usage=usage,
    )
    state.briefings[bid] = b
    return b
