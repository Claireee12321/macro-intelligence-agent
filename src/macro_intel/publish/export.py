"""Export the website data bundle (``data/site/*.json``) from state.

The site reads only these files. Display strings for numbers are produced here from the data
layer (never from LLM text). Every block carries timestamps for freshness display.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path
from typing import Any

from macro_intel import __version__
from macro_intel.analysis.llm import Budget
from macro_intel.config import Settings
from macro_intel.process.calendar import FAMILY_NAMES
from macro_intel.models import CalendarEvent, EconomicRelease, MacroEvent, MarketQuote
from macro_intel.process.indicators import fmt_value, reading
from macro_intel.process import equities, today
from macro_intel.process.scoring import display_ok
from macro_intel.store import State, atomic_write_json
from macro_intel.timeutil import ET, to_utc, utc_now

log = logging.getLogger("macro_intel")

EVENT_DAYS = 7
CAL_PAST_DAYS = 7
CAL_AHEAD_DAYS = 21
MARKET_GROUPS = [
    ("treasury", "US Treasury yields (official, end of day)"),
    ("treasury_live", "Treasury indications (intraday, delayed)"),
    ("curve", "Yield curve"),
    ("real", "Real yields & inflation expectations"),
    ("policy", "Policy & money-market rates"),
    ("fx", "US dollar & FX"),
    ("credit", "Credit & financial conditions"),
    ("commodities", "Commodities"),
    ("equities", "Equities (secondary reference)"),
]
TOPIC_GROUPS = [
    ("inflation", "Inflation"), ("labor", "Labor market"), ("growth", "Growth & activity"),
    ("housing", "Housing"), ("monetary_policy", "Monetary policy"), ("rates", "Rates"),
    ("financial_conditions", "Financial conditions & liquidity"), ("fiscal_policy", "Fiscal"),
]


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


def release_view(r: EconomicRelease, specs: dict) -> dict[str, Any]:
    spec = specs.get(r.indicator_id)

    def f(v):
        if v is None:
            return None
        return fmt_value(v, spec) if spec and r.indicator_id != "us_fed_upper" else f"{v:.{r.decimals}f}%"

    d = r.model_dump(mode="json")
    d.update(actual_display=f(r.actual), previous_display=f(r.previous), consensus_display=f(r.consensus),
             previous_first_print_display=f(r.previous_first_print))
    if r.surprise is not None and spec:
        unit = "pp" if r.units.startswith("%") else r.units
        d["surprise_display"] = f"{r.surprise:+.{r.decimals}f}{unit}" if r.surprise_direction != "in_line" else "in line"
    return d


def event_view(ev: MacroEvent, state: State, specs: dict, full: bool = True) -> dict[str, Any]:
    items = sorted((state.items[i] for i in ev.item_ids if i in state.items),
                   key=lambda i: (i.source_tier, -(i.relevance), to_utc(i.published_at or i.collected_at)))
    v: dict[str, Any] = {
        "id": ev.id, "kind": ev.kind, "title": ev.title, "region": ev.region, "topics": ev.topics,
        "importance": ev.importance, "importance_reasons": ev.importance_reasons,
        "first_published_at": _iso(ev.first_published_at), "last_published_at": _iso(ev.last_published_at),
        "first_seen_at": _iso(ev.first_seen_at), "updated_at": _iso(ev.updated_at),
        "source_count": len(ev.source_ids) or (1 if ev.release_ids else 0), "has_official_source": ev.has_official_source,
        "analysis_status": ev.analysis_status,
        "summary": ev.analysis.output.summary if ev.analysis else (items[0].summary if items else ""),
        "lead_source": items[0].source_name if items else (state.releases[ev.release_ids[0]].source_name if ev.release_ids and ev.release_ids[0] in state.releases else ""),
        "lead_url": items[0].url if items else "",
        "released_at": _iso(min((r.release_time for r in (state.releases.get(x) for x in ev.release_ids)
                                 if r is not None and r.release_time is not None), default=None)),
    }
    if not full:
        return v
    v["items"] = [{"id": i.id, "source_id": i.source_id, "source_name": i.source_name, "source_kind": i.source_kind,
                   "url": i.url, "title": i.title, "summary": i.summary, "published_at": _iso(i.published_at),
                   "published_estimated": i.published_estimated, "collected_at": _iso(i.collected_at),
                   "relevance": i.relevance} for i in items]
    v["releases"] = [release_view(state.releases[r], specs) for r in ev.release_ids if r in state.releases]
    v["analysis"] = ev.analysis.model_dump(mode="json") if ev.analysis else None
    v["observed_reaction"] = ev.observed_reaction.model_dump(mode="json") if ev.observed_reaction else None
    return v


def quote_view(q: MarketQuote) -> dict[str, Any]:
    d = q.model_dump(mode="json")
    d["history"] = [[a, b] for a, b in q.history]
    return d


MINOR_G10_CB_FAMILIES = {"boc", "rba", "rbnz", "snb", "riksbank", "norges"}


def calendar_visible(c: CalendarEvent) -> bool:
    """US: high + medium. Euro area/UK/Japan/China: high only. Other G10: central-bank decisions only."""
    if c.country == "USD":
        return c.importance in ("high", "medium")
    if c.country in ("EUR", "GBP", "JPY", "CNY"):
        return c.importance == "high"
    return c.importance == "high" and c.family in MINOR_G10_CB_FAMILIES


def calendar_rows(state: State) -> list[dict[str, Any]]:
    today = utc_now().astimezone(ET).date()
    lo, hi = today - timedelta(days=CAL_PAST_DAYS), today + timedelta(days=CAL_AHEAD_DAYS)
    groups: dict[tuple, list[CalendarEvent]] = {}
    for c in state.calendar.values():
        if not (lo <= c.date <= hi) or not calendar_visible(c):
            continue
        key = (c.date.isoformat(), c.country, c.family) if c.family else (c.key,)
        groups.setdefault(key, []).append(c)
    rank = {"high": 3, "medium": 2, "low": 1}
    rows = []
    for key, cs in groups.items():
        cs.sort(key=lambda c: (c.scheduled_at is None, c.scheduled_at or to_utc(utc_now()), c.title))
        head = cs[0]
        times = [c.scheduled_at for c in cs if c.scheduled_at]
        status = "released" if any(c.status == "released" for c in cs) else ("upcoming" if any(c.status == "upcoming" for c in cs) else "past")
        fam = head.family
        title = FAMILY_NAMES.get(fam, head.title) if fam and len(cs) > 1 else head.title
        rows.append({
            "key": "|".join(str(k) for k in key), "date": head.date.isoformat(),
            "scheduled_at": _iso(min(times)) if times else None, "all_day": not times,
            "country": head.country, "region": head.region, "family": fam, "title": title,
            "importance": max((c.importance for c in cs), key=lambda i: rank[i]), "status": status,
            "lines": [{"title": c.title, "consensus": c.consensus, "consensus_source": c.consensus_source,
                       "previous": c.previous, "previous_source": c.previous_source, "actual": c.actual,
                       "actual_source": c.actual_source, "release_id": c.release_id,
                       "scheduled_at": _iso(c.scheduled_at)} for c in cs],
            "sources": sorted({s for c in cs for s in c.sources}),
            "url": next((c.url for c in cs if c.url and "forexfactory" not in c.url), head.url),
        })
    rows.sort(key=lambda r: (r["date"], r["scheduled_at"] or "99", -rank[r["importance"]]))
    return rows


def build_bundle(state: State, settings: Settings, *, is_sample: bool = False) -> dict[str, Any]:
    now = utc_now()
    specs = {s.id: s for s in settings.indicators}
    cut = now - timedelta(days=EVENT_DAYS)
    shown = [e for e in state.events.values()
             if display_ok(e) and to_utc(e.last_published_at or e.first_seen_at) >= cut]
    shown.sort(key=lambda e: to_utc(e.last_published_at or e.first_seen_at), reverse=True)
    top = sorted([e for e in shown if to_utc(e.last_published_at or e.first_seen_at) >= now - timedelta(hours=36)],
                 key=lambda e: -e.importance)[:6]

    snap = state.latest_snapshot
    quotes = snap.quotes if snap else {}
    groups = []
    for gid, label in MARKET_GROUPS:
        qs = [quote_view(q) for q in quotes.values() if q.group == gid]
        if qs:
            groups.append({"id": gid, "label": label, "quotes": qs})

    readings = [reading(s, state.series.get(s.series_id)) for s in settings.indicators if s.display]
    eco_groups = []
    for tid, label in TOPIC_GROUPS:
        rows = [r.__dict__ for r in readings if r.topic == tid]
        if rows:
            eco_groups.append({"id": tid, "label": label, "indicators": rows})

    cal = calendar_rows(state)
    today_iso = now.astimezone(ET).date().isoformat()
    upcoming = [r for r in cal if r["status"] == "upcoming" and r["importance"] == "high"][:8]
    recent_releases = sorted((r for r in state.releases.values() if to_utc(r.detected_at) >= now - timedelta(days=7)),
                             key=lambda r: to_utc(r.release_time or r.detected_at), reverse=True)
    briefings = sorted(state.briefings.values(), key=lambda b: b.generated_at, reverse=True)
    last_run = state.runs[-1].model_dump(mode="json") if state.runs else None
    calls, spent = Budget(state, settings).spent_today()

    meta = {
        "app": "Macro Intelligence Agent", "version": __version__, "generated_at": now.isoformat(),
        "is_sample": is_sample,
        "mode": "sample" if is_sample else ("ai" if settings.llm_enabled else "data-only"),
        "schedule": "Updated automatically once per weekday at about 10:05 ET (GitHub Actions; start time approximate).",
        "last_run": last_run,
        "llm": {"enabled": settings.llm_enabled, "provider": settings.llm_provider, "model": settings.llm_model if settings.llm_enabled else None,
                "calls_today": calls, "cost_today_usd": spent, "daily_budget_usd": settings.llm_daily_budget_usd},
        "fred_api": bool(settings.fred_api_key),
        "source_health": state.meta.get("source_health", {}),
        "market_source_status": snap.source_status if snap else {},
        "stale_site_after_hours": 30,
    }
    return {
        "meta.json": meta,
        "overview.json": {
            "generated_at": now.isoformat(),
            "today": {
                "central_bank_decisions": today.policy_decisions(state),
                "key_releases": [release_view(r, specs) for r in today.key_releases(state)],
                "us_equities": (lambda eq: eq.model_dump(mode="json") if eq else None)(equities.summarize(state)),
            },
            "macro_state": state.macro_state.model_dump(mode="json") if state.macro_state else None,
            "briefing": briefings[0].model_dump(mode="json") if briefings else None,
            "top_events": [event_view(e, state, specs, full=False) for e in top],
            "key_markets": [quote_view(q) for q in quotes.values() if any(s.id == q.id and s.overview for s in settings.markets)],
            "upcoming": upcoming,
            "recent_releases": [release_view(r, specs) for r in recent_releases[:10]],
            "today_date": today_iso,
        },
        "events.json": {"generated_at": now.isoformat(), "events": [event_view(e, state, specs) for e in shown]},
        "calendar.json": {"generated_at": now.isoformat(), "rows": cal},
        "markets.json": {"generated_at": now.isoformat(), "snapshot_taken_at": _iso(snap.taken_at) if snap else None,
                         "groups": groups, "source_status": snap.source_status if snap else {}},
        "economy.json": {"generated_at": now.isoformat(), "groups": eco_groups},
        "briefings.json": {"generated_at": now.isoformat(), "briefings": [b.model_dump(mode="json") for b in briefings[:30]]},
        "sources.json": {"generated_at": now.isoformat(), "sources": [
            {**s.model_dump(mode="json"), "health": state.meta.get("source_health", {}).get(s.id)} for s in settings.sources]},
    }


def write_bundle(bundle: dict[str, Any], site_dir: Path) -> None:
    for name, payload in bundle.items():
        atomic_write_json(Path(site_dir) / name, payload)
    log.info("Exported %d site files to %s", len(bundle), site_dir)
