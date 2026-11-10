"""Deduplication and incremental event clustering.

1. Exact dedup: same canonical-URL id, or same source + same normalized title.
2. Classification + relevance scoring of genuinely new items.
3. Clustering of relevant items into MacroEvents:
   - shared *specific* concept family (e.g. cpi, fed, ecb) + same region + ≤36h + some lexical overlap
   - shared broad concept + ≤24h + clear lexical overlap
   - near-duplicate headline (Jaccard ≥ 0.5) within 48h
   Events are never merged across incompatible regions (US CPI ≠ euro-area CPI).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta

from macro_intel.models import EconomicRelease, MacroEvent, NewsItem, NewsSource
from macro_intel.process.classify import classify, families, specific_families
from macro_intel.process.scoring import score_event, score_item
from macro_intel.process.text import jaccard, normalized_title_key, stable_id, title_tokens
from macro_intel.store import State
from macro_intel.timeutil import to_utc, utc_now

log = logging.getLogger("macro_intel")

EVENT_MIN_ITEM_RELEVANCE = 35.0
_MARKET_WRAP = re.compile(r"live updates|markets? wrap|stock market today|\b(dow|s&p 500|nasdaq|wall street)\b", re.I)
CANDIDATE_WINDOW = timedelta(hours=72)
OFFICIAL_DUP_WINDOW = timedelta(days=7)
# Families whose stories turn over quickly (a crash today ≠ yesterday's rally): tighter window.
FAMILY_MAX_HOURS = {"market_shock": 12.0}  # measured from the episode's first item (no chaining)
FAMILY_MIN_JACCARD = {"market_shock": 0.0}  # market-move headlines share few words; timing + region decide
_WEAK_FAMILIES = {"equity_market", "growth_general", "inflation_general", "labor_general", "fx", "metals", "cb_speak", "rate_decision"}


def item_time(item: NewsItem) -> datetime:
    return to_utc(item.published_at or item.collected_at)


def ingest_items(state: State, raw_items: list[NewsItem], sources: dict[str, NewsSource]) -> list[NewsItem]:
    """Dedup against state, classify & score new items, add them to state. Returns new items."""
    title_index = {(i.source_id, normalized_title_key(i.title)) for i in state.items.values()}
    added: list[NewsItem] = []
    for raw in raw_items:
        if raw.id in state.items:
            existing = state.items[raw.id]
            if not existing.summary and raw.summary:
                existing.summary = raw.summary
            continue
        key = (raw.source_id, normalized_title_key(raw.title))
        if key in title_index:
            continue
        src = sources.get(raw.source_id)
        if src is None:
            continue
        cls = classify(raw.title, raw.summary, src)
        raw.concepts = cls.concepts
        raw.topics = cls.topics
        raw.region = cls.region  # type: ignore[assignment]
        raw.relevance, raw.relevance_reasons = score_item(raw, cls)
        state.items[raw.id] = raw
        title_index.add(key)
        added.append(raw)
    log.info("Dedup: %d raw → %d new items", len(raw_items), len(added))
    return added


def rescore_items(state: State, sources: dict[str, NewsSource]) -> int:
    """Re-apply the current classification/scoring rules to every stored item (cheap; keeps rule
    changes effective immediately). Cluster membership is unchanged; events refresh afterwards."""
    n = 0
    for it in state.items.values():
        src = sources.get(it.source_id)
        if src is None:
            continue
        cls = classify(it.title, it.summary, src)
        it.concepts, it.topics, it.region = cls.concepts, cls.topics, cls.region  # type: ignore[assignment]
        it.relevance, it.relevance_reasons = score_item(it, cls)
        n += 1
    return n


def _region_ok(a: str, b: str, strict: bool) -> bool:
    if a == b:
        return True
    if strict:
        return False
    return "Global" in (a, b)


class _EventIndex:
    """Token cache for candidate events during one clustering pass."""

    def __init__(self, state: State):
        self.state = state
        self.tokens: dict[str, list[frozenset[str]]] = {}

    def event_tokens(self, ev: MacroEvent) -> list[frozenset[str]]:
        if ev.id not in self.tokens:
            toks = [title_tokens(self.state.items[i].title) for i in ev.item_ids[-15:] if i in self.state.items]
            toks.append(title_tokens(ev.title))
            self.tokens[ev.id] = toks
        return self.tokens[ev.id]

    def add(self, ev: MacroEvent, toks: frozenset[str]) -> None:
        self.tokens.setdefault(ev.id, []).append(toks)


def _match_score(item: NewsItem, toks: frozenset[str], ev: MacroEvent, idx: _EventIndex, state: State) -> float | None:
    t_item = item_time(item)
    t_ev = to_utc(ev.last_published_at or ev.first_seen_at)
    hours = abs((t_item - t_ev).total_seconds()) / 3600.0
    j = max((jaccard(toks, t) for t in idx.event_tokens(ev)), default=0.0)
    same_official_source = item.source_kind == "official" and item.source_id in ev.source_ids
    if same_official_source and j >= 0.5 and hours <= OFFICIAL_DUP_WINDOW.total_seconds() / 3600.0:
        return j  # e.g. the same report republished in another format days later
    if hours > CANDIDATE_WINDOW.total_seconds() / 3600.0:
        return None
    # Official sources publish distinct releases; only merge same-source items on near-identical titles.
    item_fams, ev_fams = families(item.concepts), families(ev.concepts)
    shared_specific = (specific_families(item.concepts) & ev_fams) | (specific_families(ev.concepts) & item_fams)
    if same_official_source:
        # Meeting outputs (decision, statement, outlook) are published within hours of each other.
        if shared_specific & specific_families(item.concepts) & specific_families(ev.concepts) and hours <= 3:
            return 0.5 + j
        return j if j >= 0.5 else None
    shared_broad = (item_fams & ev_fams) - shared_specific - _WEAK_FAMILIES
    if shared_specific and set(shared_specific) <= set(FAMILY_MAX_HOURS):
        since_first = abs((t_item - to_utc(ev.first_published_at or ev.first_seen_at)).total_seconds()) / 3600.0
        if since_first <= min(FAMILY_MAX_HOURS[f] for f in shared_specific) and \
                j >= min(FAMILY_MIN_JACCARD.get(f, 0.05) for f in shared_specific) and \
                _region_ok(item.region, ev.region, strict=True):
            return 0.5 + j
        shared_specific = set()
    if shared_specific and hours <= 36 and _region_ok(item.region, ev.region, strict=True):
        # Official data-release events anchor on the release itself: same-family coverage belongs to it.
        if ev.kind == "data_release" and shared_specific & specific_families(item.concepts):
            return 0.6 + j
        if j >= 0.05:  # same release/decision family, same region, ≤36h: minimal lexical overlap suffices
            return 0.5 + j
    if shared_broad and hours <= 24 and j >= 0.30 and _region_ok(item.region, ev.region, strict=False):
        return 0.3 + j
    if hours <= 48 and j >= 0.5 and _region_ok(item.region, ev.region, strict=False):
        return j
    return None


def assign_events(state: State, new_items: list[NewsItem]) -> tuple[int, int]:
    """Attach relevant new items to events (or create events). Returns (attached, created)."""
    now = utc_now()
    idx = _EventIndex(state)
    attached = created = 0
    candidates = [i for i in new_items if i.relevance >= EVENT_MIN_ITEM_RELEVANCE]
    candidates.sort(key=item_time)
    for item in candidates:
        toks = title_tokens(item.title)
        window = OFFICIAL_DUP_WINDOW if item.source_kind == "official" else CANDIDATE_WINDOW
        open_events = [
            e for e in state.events.values()
            if to_utc(e.last_published_at or e.first_seen_at) >= item_time(item) - window
        ]
        best, best_score = None, 0.0
        for ev in open_events:
            s = _match_score(item, toks, ev, idx, state)
            if s is not None and s > best_score:
                best, best_score = ev, s
        if best is None:
            ev = MacroEvent(
                id="ev_" + stable_id(item.id),
                title=item.title,
                region=item.region,
                topics=list(item.topics),
                concepts=list(item.concepts),
                item_ids=[item.id],
                source_ids=[item.source_id],
                first_published_at=item_time(item),
                last_published_at=item_time(item),
                first_seen_at=now,
                updated_at=now,
            )
            state.events[ev.id] = ev
            idx.add(ev, toks)
            item.event_id = ev.id
            created += 1
        else:
            best.item_ids.append(item.id)
            best.updated_at = now
            idx.add(best, toks)
            item.event_id = best.id
            attached += 1
    for ev_id in {i.event_id for i in candidates if i.event_id}:
        refresh_event(state, state.events[ev_id])
    log.info("Clustering: %d new items attached, %d events created", attached, created)
    return attached, created


def _release_day(state: State, ev: MacroEvent) -> tuple[str, str] | None:
    for rid in ev.release_ids:
        r = state.releases.get(rid)
        if r:
            t = to_utc(r.release_time or r.detected_at)
            return (r.family or r.indicator_id, t.date().isoformat())
    return None


def attach_release(state: State, release: EconomicRelease, title: str, event: MacroEvent | None = None) -> MacroEvent:
    """Find or create the event for an official release (one event per family per release day)."""
    now = utc_now()
    rel_time = to_utc(release.release_time or release.detected_at)
    family = release.family or release.indicator_id
    key = (family, rel_time.date().isoformat())
    ev = event or state.events.get("rel_" + stable_id(*key))
    if ev is None:
        # An event already carrying a release of this family on this day (e.g. headline CPI attached
        # earlier in this run or a previous run) takes precedence…
        ev = next((e for e in state.events.values() if e.release_ids and _release_day(state, e) == key), None)
    if ev is None:
        # …then a recent news event about the same release family and region.
        for cand in state.events.values():
            if cand.kind == "news" and family in families(cand.concepts) and cand.region == release.region:
                t = to_utc(cand.last_published_at or cand.first_seen_at)
                if abs((t - rel_time).total_seconds()) <= 36 * 3600:
                    ev = cand
                    break
    if ev is None:
        ev = MacroEvent(
            id="rel_" + stable_id(*key),
            kind="data_release",
            title=title,
            region=release.region,
            topics=[release.topic],
            concepts=[family],
            first_published_at=rel_time,
            last_published_at=rel_time,
            first_seen_at=now,
            updated_at=now,
            has_official_source=True,
        )
        state.events[ev.id] = ev
    ev.kind = "data_release"
    ev.title = title
    ev.has_official_source = True
    if release.id not in ev.release_ids:
        ev.release_ids.append(release.id)
    if family not in families(ev.concepts):
        ev.concepts.append(family)
    ev.updated_at = now
    release.event_id = ev.id
    refresh_event(state, ev)
    return ev


def merge_duplicate_release_events(state: State) -> int:
    """Self-heal: merge data-release events that carry the same release family on the same day."""
    groups: dict[tuple[str, str], list[MacroEvent]] = {}
    for ev in state.events.values():
        if ev.kind == "data_release" and ev.release_ids:
            k = _release_day(state, ev)
            if k:
                groups.setdefault(k, []).append(ev)
    merged = 0
    for evs in groups.values():
        if len(evs) < 2:
            continue
        evs.sort(key=lambda e: (-len(e.release_ids), -len(e.item_ids), e.first_seen_at))
        keep, rest = evs[0], evs[1:]
        for dup in rest:
            for rid in dup.release_ids:
                if rid not in keep.release_ids:
                    keep.release_ids.append(rid)
                if rid in state.releases:
                    state.releases[rid].event_id = keep.id
            for iid in dup.item_ids:
                if iid not in keep.item_ids:
                    keep.item_ids.append(iid)
                if iid in state.items:
                    state.items[iid].event_id = keep.id
            for c in dup.concepts:
                if c not in keep.concepts:
                    keep.concepts.append(c)
            del state.events[dup.id]
            merged += 1
        refresh_event(state, keep)
    return merged


def refresh_event(state: State, ev: MacroEvent) -> None:
    items = [state.items[i] for i in ev.item_ids if i in state.items]
    releases = [state.releases[r] for r in ev.release_ids if r in state.releases]
    if items:
        ev.source_ids = sorted({i.source_id for i in items})
        ev.has_official_source = ev.has_official_source or any(i.source_kind == "official" for i in items)
        times = [item_time(i) for i in items]
        if releases:
            times += [to_utc(r.release_time or r.detected_at) for r in releases]
        ev.first_published_at = min(times)
        ev.last_published_at = max(times)
        concepts: list[str] = list(ev.concepts) if ev.kind == "data_release" else []
        topics: list[str] = list(ev.topics) if ev.kind == "data_release" else []
        for i in sorted(items, key=lambda x: -x.relevance):
            for c in i.concepts:
                if c not in concepts:
                    concepts.append(c)
            for t in i.topics:
                if t not in topics:
                    topics.append(t)
        ev.concepts, ev.topics = concepts, topics or ["other"]
        if ev.kind == "news":
            ranked = sorted(items, key=lambda x: (x.source_tier, -x.relevance, item_time(x)))
            rep = ranked[0]
            shock = sum("market_shock" in i.concepts for i in items)
            if shock * 2 >= len(items):  # a market episode: prefer a market-wrap headline as the title
                wraps = sorted((i for i in items if _MARKET_WRAP.search(i.title)), key=item_time, reverse=True)
                rep = wraps[0] if wraps else rep  # the latest wrap describes the episode best
                ev.topics = ["financial_conditions"] + [t for t in ev.topics if t != "financial_conditions"]
            ev.title = rep.title
            weights: dict[str, float] = {}
            for i in items:
                weights[i.region] = weights.get(i.region, 0.0) + i.relevance
            ev.region = max(weights, key=weights.get)  # type: ignore[assignment]
    ev.importance, ev.importance_reasons = score_event(ev, items, releases)
