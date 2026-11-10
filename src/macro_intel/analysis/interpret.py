"""Stage 1: per-event economic interpretation (only for new or materially changed important events)."""

from __future__ import annotations

import json
import logging
from datetime import timedelta

from macro_intel.analysis import context
from macro_intel.analysis.llm import Budget, Provider, call_structured
from macro_intel.analysis.prompts import EVENT_PROMPT_VERSION, EVENT_SYSTEM
from macro_intel.config import Settings
from macro_intel.models import AnalysisRecord, EventAnalysis, MacroEvent
from macro_intel.process.scoring import display_ok
from macro_intel.process.text import stable_id
from macro_intel.store import State
from macro_intel.timeutil import fmt_et, hours_since, to_utc, utc_now

log = logging.getLogger("macro_intel")

MAX_ITEMS_IN_PACKET = 10
RECENT_WINDOW = timedelta(hours=48)
MAX_ATTEMPTS = 2


def _packet_items(state: State, ev: MacroEvent):
    items = [state.items[i] for i in ev.item_ids if i in state.items]
    items.sort(key=lambda i: (i.source_tier, -i.relevance))
    return items[:MAX_ITEMS_IN_PACKET]


def input_hash(state: State, ev: MacroEvent) -> str:
    items = _packet_items(state, ev)
    return stable_id(*sorted(i.id for i in items), *sorted(ev.release_ids), length=20)


def needs_analysis(state: State, ev: MacroEvent, settings: Settings) -> bool:
    if ev.importance < settings.llm_min_importance or not display_ok(ev):
        return False
    if utc_now() - to_utc(ev.last_published_at or ev.first_seen_at) > RECENT_WINDOW:
        return False
    if ev.analysis is None:
        return not (ev.analysis_status == "failed" and ev.analysis_attempts >= MAX_ATTEMPTS)
    if ev.analysis.input_hash == input_hash(state, ev):
        return False
    if (hours_since(ev.analysis.generated_at) or 0) < settings.llm_reanalysis_cooldown_hours:
        return False
    # Material change only: a new official release, or substantial new primary/official coverage.
    new_releases = set(ev.release_ids) - set(ev.analysis.input_release_ids)
    new_items = [state.items[i] for i in ev.item_ids if i in state.items and i not in ev.analysis.input_item_ids]
    return bool(new_releases) or any(i.source_kind == "official" for i in new_items) or len(new_items) >= 3


def build_packet(state: State, ev: MacroEvent) -> tuple[str, dict[str, str]]:
    """Return (JSON packet, short-ref → real-id map)."""
    refs: dict[str, str] = {}
    sources = []
    for n, it in enumerate(_packet_items(state, ev), 1):
        ref = f"I{n}"
        refs[ref] = it.id
        sources.append({"ref": ref, "source": it.source_name, "kind": it.source_kind,
                        "published": fmt_et(it.published_at) or "unknown", "title": it.title,
                        **({"summary": it.summary} if it.summary else {})})
    data = []
    for n, rid in enumerate(ev.release_ids, 1):
        r = state.releases.get(rid)
        if not r:
            continue
        ref = f"R{n}"
        refs[ref] = r.id
        row = {"ref": ref, "indicator": r.name, "period": r.period_label, "units": r.units,
               "actual": round(r.actual, r.decimals + 1), "previous": None if r.previous is None else round(r.previous, r.decimals + 1),
               "released": fmt_et(r.release_time), "source": r.source_name}
        if r.consensus is not None:
            row["consensus"] = r.consensus
            row["consensus_source"] = r.consensus_source
            row["surprise_vs_consensus"] = r.surprise
        else:
            row["consensus"] = "unavailable"
            row["consensus_note"] = r.consensus_note
        if r.previous_first_print is not None:
            row["previous_first_print"] = r.previous_first_print
        data.append(row)
    reaction = None
    if ev.observed_reaction:
        reaction = {"window": ev.observed_reaction.window, "final": ev.observed_reaction.final,
                    "moves": [{"instrument": m.label, "from": m.start_label, "to": m.end_label,
                               "change": m.change, "units": m.change_units} for m in ev.observed_reaction.moves],
                    "caveats": ev.observed_reaction.caveats}
    packet = {
        "now": context.now_line(),
        "event": {"title": ev.title, "kind": ev.kind, "region": ev.region, "topics": ev.topics,
                  "first_published": fmt_et(ev.first_published_at), "distinct_sources": len(ev.source_ids)},
        "sources": sources,
        "official_data": data,
        "macro_state": context.regime_lines(state.macro_state),
        "market_context": context.market_lines(state.latest_snapshot),
        "observed_reaction": reaction,
        "upcoming_calendar": context.upcoming_lines(state),
    }
    return json.dumps(packet, ensure_ascii=False, indent=1), refs


def _map_refs(out: EventAnalysis, refs: dict[str, str]) -> list[str]:
    dropped: list[str] = []
    for f in out.facts:
        mapped = []
        for r in f.refs:
            if r in refs:
                mapped.append(refs[r])
            else:
                dropped.append(r)
        f.refs = mapped
    return dropped


def run_event_analyses(state: State, settings: Settings, provider: Provider | None) -> dict[str, int]:
    counts = {"candidates": 0, "analyzed": 0, "failed": 0, "skipped_budget": 0}
    events = sorted(state.events.values(), key=lambda e: -e.importance)
    candidates = [e for e in events if needs_analysis(state, e, settings)]
    counts["candidates"] = len(candidates)
    if provider is None:
        for e in candidates:
            if e.analysis is None:
                e.analysis_status = "skipped_no_llm"
        return counts
    budget = Budget(state, settings)
    for ev in candidates[: settings.llm_max_event_analyses_per_run]:
        packet, refs = build_packet(state, ev)
        parsed, usage, err = call_structured(provider, budget, f"event:{ev.id}", EVENT_SYSTEM, packet, EventAnalysis)
        if parsed is None:
            if err.startswith("budget"):
                ev.analysis_status = "skipped_budget" if ev.analysis is None else ev.analysis_status
                counts["skipped_budget"] += 1
                break
            ev.analysis_attempts += 1
            ev.analysis_status = "failed" if ev.analysis is None else ev.analysis_status
            counts["failed"] += 1
            continue
        dropped = _map_refs(parsed, refs)
        items = _packet_items(state, ev)
        ev.analysis = AnalysisRecord(
            event_id=ev.id, generated_at=utc_now(), provider=provider.name, model=provider.model,
            prompt_version=EVENT_PROMPT_VERSION, input_hash=input_hash(state, ev),
            input_item_ids=[i.id for i in items], input_release_ids=list(ev.release_ids),
            output=parsed, usage=usage, dropped_refs=dropped,
        )
        ev.analysis_status = "done"
        ev.analysis_attempts += 1
        counts["analyzed"] += 1
    return counts
