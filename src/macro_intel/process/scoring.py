"""Deterministic relevance (items) and importance (events) scoring, 0–100, with reasons.

Item relevance = (65 × macro_core + source tier points + cross-topic bonus) × region multiplier,
minus penalties for noise / routine official publications.

* macro_core  = max over matched concepts of topic_weight × strength_factor
                (title concepts full weight; summary-only concepts half; source default topic 0.3)
* region mult = 0.55 + 0.45 × region_weight   (US 1.0 … Other 0.25)

Event importance adds a capped, logarithmic coverage-breadth bonus (so a story is not
over-weighted just because many outlets ran it), an official-source bonus, and bonuses for
linked official releases and consensus surprises.
"""

from __future__ import annotations

import math

from macro_intel.models import EconomicRelease, MacroEvent, NewsItem
from macro_intel.process.classify import (
    OUT_OF_COVERAGE_CAP,
    REGION_WEIGHTS,
    STRENGTH_FACTOR,
    TOPIC_WEIGHTS,
    Classification,
    concept,
)

ITEM_DISPLAY_THRESHOLD = 40.0  # items below are kept but not shown by default
EVENT_DISPLAY_THRESHOLD = 45.0

# Coverage policy (owner, 2026-11-05): US first; other G10 economies + China only when something
# material happens — a central-bank decision, a top-tier data release, or a big market/leadership story.
MAJOR_NON_US = {"EA", "UK", "JP", "CN"}
MINOR_G10 = {"CA", "AU", "NZ", "CH", "SE", "NO"}
NON_US_DISPLAY_THRESHOLD = 55.0

_TIER_POINTS = {1: 15, 2: 10, 3: 5}


def score_item(item: NewsItem, cls: Classification) -> tuple[float, list[str]]:
    reasons: list[str] = []
    best, best_id = 0.0, None
    for cid in cls.concepts:
        c = concept(cid)
        if c:
            v = TOPIC_WEIGHTS.get(c.topic, 0.1) * STRENGTH_FACTOR[c.strength]
            if v > best:
                best, best_id = v, cid
    for cid in cls.summary_concepts:
        c = concept(cid)
        if c:
            v = 0.5 * TOPIC_WEIGHTS.get(c.topic, 0.1) * STRENGTH_FACTOR[c.strength]
            if v > best:
                best, best_id = v, f"{cid} (summary)"
    if best == 0.0:
        default_topic = cls.topics[0] if cls.topics else "other"
        best = 0.3 * TOPIC_WEIGHTS.get(default_topic, 0.1)
        best_id = f"source default topic {default_topic}"

    pts = 65 * best
    reasons.append(f"macro core {best_id} (+{65 * best:.0f})")
    tier_pts = _TIER_POINTS.get(item.source_tier, 5)
    pts += tier_pts
    reasons.append(f"{item.source_kind} source, tier {item.source_tier} (+{tier_pts})")

    strong = [concept(c) for c in cls.concepts if concept(c) and concept(c).strength == "high"]
    other_topics = {
        concept(c).topic for c in cls.concepts
        if concept(c) and concept(c).strength in ("high", "medium") and concept(c).topic not in ("equities", "other")
    }
    if strong and len(other_topics) >= 2:
        pts += 10
        reasons.append("high-impact concept spanning several macro topics (+10)")

    region_w = REGION_WEIGHTS.get(cls.region, 0.25)
    mult = 0.55 + 0.45 * region_w
    pts *= mult
    reasons.append(f"region {cls.region} (×{mult:.2f})")

    if cls.noise:
        pts -= 40
        reasons.append("non-macro / noise pattern (-40)")
    if cls.routine_official:
        pts -= 40
        reasons.append("routine official publication (-40)")

    if cls.region == "Other" and pts > OUT_OF_COVERAGE_CAP:
        pts = OUT_OF_COVERAGE_CAP
        reasons.append(f"outside coverage (G10 + China): capped at {OUT_OF_COVERAGE_CAP:.0f}")

    return round(max(0.0, min(100.0, pts)), 1), reasons


def score_event(event: MacroEvent, items: list[NewsItem], releases: list[EconomicRelease]) -> tuple[float, list[str]]:
    reasons: list[str] = []
    base = max((i.relevance for i in items), default=0.0)
    if base:
        reasons.append(f"top item relevance {base:.0f}")
    if releases:
        rel_base = max(85.0 if r.importance == "high" else 70.0 if r.importance == "medium" else 55.0 for r in releases)
        if rel_base > base:
            base = rel_base
            reasons.append(f"official data release ({rel_base:.0f})")

    n_sources = len(set(event.source_ids))
    breadth = min(10.0, 5.0 * math.log2(n_sources)) if n_sources > 1 else 0.0
    if breadth:
        reasons.append(f"{n_sources} distinct sources (+{breadth:.0f}, capped)")

    official = 5.0 if event.has_official_source and base >= 50 else 0.0
    if official:
        reasons.append("primary/official source (+5)")

    surprise = 0.0
    for r in releases:
        if r.surprise_direction in ("above", "below"):
            surprise = 5.0
            reasons.append(f"{r.short} {r.surprise_direction} consensus (+5)")
            break

    return round(min(100.0, base + breadth + official + surprise), 1), reasons


def _has_strong_concept(ev: MacroEvent) -> bool:
    return any((c := concept(cid)) is not None and c.strength == "high" for cid in ev.concepts)


def display_ok(ev: MacroEvent) -> bool:
    """Whether an event surfaces on the site / in briefings / for LLM analysis."""
    if ev.importance < EVENT_DISPLAY_THRESHOLD:
        return False
    if ev.region == "US" or ev.kind == "data_release":
        return True
    strong = _has_strong_concept(ev)
    broad = len(set(ev.source_ids)) >= 3
    if ev.region == "Global":
        return ev.importance >= 50 and (strong or len(set(ev.source_ids)) >= 2)
    if ev.region in MAJOR_NON_US:
        return ev.importance >= NON_US_DISPLAY_THRESHOLD and (strong or broad)
    if ev.region in MINOR_G10:
        return ev.importance >= NON_US_DISPLAY_THRESHOLD and strong
    return False  # outside coverage
