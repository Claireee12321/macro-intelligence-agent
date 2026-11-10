"""Detect new official data prints and turn them into EconomicRelease facts.

Rules that protect against look-ahead and invented expectations:
* A release is created only when a *new* period appears in the official series (or, for
  revision-tracked series like GDP, the latest period's value changes on a scheduled day).
* On the first run for a series (bootstrap) we only create a release if there is evidence it was
  published in the last few days (FRED realtime_start or a matching calendar row) — we never
  backfill history as "new".
* Consensus comes only from a matched calendar row's published forecast (source named). If none
  exists, consensus is None and ``consensus_note`` says so explicitly. "Previous" is never used.
* Surprise is computed at the indicator's published precision.
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta

from macro_intel.process.calendar import FAMILY_NAMES
from macro_intel.models import CalendarEvent, EconomicRelease, IndicatorSpec
from macro_intel.process.cluster import attach_release
from macro_intel.process.indicators import fmt_value, period_label, transform
from macro_intel.store import State
from macro_intel.timeutil import ET, et_datetime, utc_now

log = logging.getLogger("macro_intel")

RECENT_DAYS = 4
_FF_VALUE = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*([KMBT%]?)\s*$", re.I)
_MULT = {"": 1.0, "K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}


def parse_forecast(text: str | None, spec: IndicatorSpec) -> float | None:
    """Parse a calendar forecast like '0.3%', '65K', '7.15M' into the indicator's units."""
    if not text:
        return None
    m = _FF_VALUE.match(text)
    if not m:
        return None
    num, suffix = float(m.group(1)), m.group(2).upper()
    units = spec.units
    if units.startswith("%"):
        return num if suffix in ("%", "") else None
    if units in ("K", "M"):
        if suffix not in _MULT or suffix == "%":
            return None
        return num * _MULT[suffix] / _MULT[units]
    if units == "index":
        return num if suffix == "" else None
    return None


def surprise(actual: float, consensus: float, decimals: int) -> tuple[float, str]:
    a = round(actual, decimals)
    diff = round(a - consensus, decimals + 2)
    tol = 0.5 * 10 ** (-decimals)
    if abs(diff) < tol:
        return 0.0, "in_line"
    return diff, "above" if diff > 0 else "below"


def _match_calendar(state: State, spec: IndicatorSpec) -> CalendarEvent | None:
    now = utc_now()
    lo = now.date() - timedelta(days=RECENT_DAYS)
    rows = [
        c for c in state.calendar.values()
        if c.indicator_id == spec.id and lo <= c.date <= now.date() and (c.scheduled_at is None or c.scheduled_at <= now)
    ]
    return max(rows, key=lambda c: c.scheduled_at or et_datetime(c.date, 0, 0)) if rows else None


def _family_schedule(state: State, family: str | None) -> CalendarEvent | None:
    """A recent official-schedule row for the family (e.g. BEA GDP, FOMC) to time the release."""
    if not family:
        return None
    now = utc_now()
    lo = now.date() - timedelta(days=RECENT_DAYS)
    rows = [c for c in state.calendar.values() if c.family == family and lo <= c.date <= now.date()
            and (c.scheduled_at is None or c.scheduled_at <= now)]
    return max(rows, key=lambda c: c.scheduled_at or et_datetime(c.date, 0, 0)) if rows else None


def _make_release(state: State, spec: IndicatorSpec, vals, rid: str, bootstrap: bool) -> EconomicRelease | None:
    series = state.series[spec.series_id]
    d1, actual = vals[-1]
    prev = vals[-2] if len(vals) >= 2 else None
    cal = _match_calendar(state, spec)
    sched = cal or _family_schedule(state, spec.family)
    now = utc_now()

    if bootstrap:
        recent_rt = series.latest_realtime_start and (now.date() - series.latest_realtime_start).days <= RECENT_DAYS
        if not (recent_rt or cal):
            return None

    consensus = parse_forecast(cal.consensus, spec) if cal and cal.consensus else None
    rel = EconomicRelease(
        id=rid, indicator_id=spec.id, name=spec.name, short=spec.short, region=spec.region, topic=spec.topic,
        period=d1.isoformat(), period_label=period_label(d1, spec.frequency), units=spec.units, decimals=spec.decimals,
        actual=round(actual, 6), previous=round(prev[1], 6) if prev else None,
        previous_label=period_label(prev[0], spec.frequency) if prev else None,
        detected_at=now, importance=spec.importance, family=spec.family,
        source_name=("SAMPLE (synthetic)" if series.source == "sample"
                     else f"{spec.source_name} via FRED" if spec.source_name else "FRED"),
        source_url="" if series.source == "sample" else f"https://fred.stlouisfed.org/series/{spec.series_id}",
        vintage_note=f"Actual and previous from {series.vintage} fetched {series.fetched_at.astimezone(ET).strftime('%Y-%m-%d %H:%M ET')}; "
                     "previous reflects any revisions published with this release.",
    )
    if spec.notes:
        rel.notes.append(spec.notes)
    if prev and series.initial_release:
        first = series.initial_release.get(prev[0].isoformat())
        if first is not None and spec.transform == "level":
            rel.previous_first_print = round(first * spec.scale, 6)
    if cal:
        rel.calendar_key = cal.key
        if consensus is not None:
            rel.consensus, rel.consensus_source = consensus, cal.consensus_source
            rel.surprise, rel.surprise_direction = surprise(actual, consensus, spec.decimals)
        elif cal.consensus:
            rel.consensus_note = f"Published forecast '{cal.consensus}' could not be compared in {spec.units} units."
        else:
            rel.consensus_note = "No published forecast available in free sources for this release."
    else:
        rel.consensus_note = "No matching calendar entry with a published forecast; consensus unavailable."
    if sched and sched.scheduled_at:
        rel.release_time, rel.release_time_basis = sched.scheduled_at, "calendar" if sched is cal else "official_schedule"
    elif series.latest_realtime_start:
        rel.release_time, rel.release_time_basis = et_datetime(series.latest_realtime_start, 8, 30), "fred_realtime"
        rel.notes.append("Release time approximated from FRED's publication date (time of day not provided).")
    else:
        rel.release_time, rel.release_time_basis = now, "first_detected"
    return rel


def headline(family: str | None, releases: list[EconomicRelease], specs: dict[str, IndicatorSpec]) -> str:
    """Neutral, data-only event title, e.g. 'US CPI (Sep 2026): CPI m/m +0.6% (forecast +0.4%); …'."""
    order = {sid: i for i, sid in enumerate(specs)}
    rels = sorted(releases, key=lambda r: order.get(r.indicator_id, 99))
    name = FAMILY_NAMES.get(family or "", rels[0].name)
    parts = []
    for r in rels[:3]:
        spec = specs[r.indicator_id]
        txt = f"{r.short} {fmt_value(r.actual, spec)}"
        if r.consensus is not None:
            txt += f" (forecast {fmt_value(r.consensus, spec)})"
        parts.append(txt)
    prefix = "US " if rels[0].region == "US" and not name.startswith("US") else ""
    return f"{prefix}{name} ({rels[0].period_label}): " + "; ".join(parts)


def detect_releases(state: State, specs: list[IndicatorSpec]) -> list[EconomicRelease]:
    marks: dict = state.meta.setdefault("release_watermarks", {})
    new: list[EconomicRelease] = []
    for spec in specs:
        if not spec.release or spec.series_id not in state.series:
            continue
        vals = transform(spec, state.series[spec.series_id].observations)
        if not vals:
            continue
        d1, v1 = vals[-1]
        period = d1.isoformat()
        mark = marks.get(spec.id)
        rid = f"{spec.id}:{period}"
        bootstrap = mark is None
        if mark is not None:
            if period < mark["period"]:
                continue
            if period == mark["period"]:
                changed = round(v1, spec.decimals) != round(mark["value"], spec.decimals)
                if not (spec.track_revisions and changed and _family_schedule(state, spec.family)):
                    mark["value"] = v1
                    continue
                n = int(mark.get("revisions", 0)) + 1
                rid = f"{rid}:rev{n}"
                mark["revisions"] = n
        rel = None if rid in state.releases else _make_release(state, spec, vals, rid, bootstrap)
        marks[spec.id] = {"period": period, "value": v1, "revisions": marks.get(spec.id, {}).get("revisions", 0)}
        if rel is None:
            continue
        state.releases[rel.id] = rel
        new.append(rel)
        if rel.calendar_key and rel.calendar_key in state.calendar:
            row = state.calendar[rel.calendar_key]
            row.actual = fmt_value(rel.actual, spec)
            row.actual_source = rel.source_name
            row.release_id, row.status = rel.id, "released"

    # One event per family per release day.
    by_family: dict[str, list[EconomicRelease]] = {}
    for r in new:
        by_family.setdefault(r.family or r.indicator_id, []).append(r)
    spec_map = {s.id: s for s in specs}
    for fam, rels in by_family.items():
        title = headline(fam, rels, spec_map)
        ev = attach_release(state, rels[0], title)
        for r in rels[1:]:
            attach_release(state, r, title, event=ev)
    fomc = detect_fomc(state, spec_map)
    if fomc:
        new.append(fomc)
    if new:
        log.info("Releases: %d new (%s)", len(new), ", ".join(r.id for r in new))
    return new


def detect_fomc(state: State, specs: dict[str, IndicatorSpec]) -> EconomicRelease | None:
    """Structured FOMC decision once FRED shows the target range effective after the meeting."""
    upper_spec, lower_spec = specs.get("us_fed_upper"), specs.get("us_fed_lower")
    if not upper_spec or not lower_spec:
        return None
    up, lo = state.series.get(upper_spec.series_id), state.series.get(lower_spec.series_id)
    if not up or not lo:
        return None
    now = utc_now()
    meetings = [c for c in state.calendar.values() if c.family == "fed" and "federalreserve.gov" in c.sources
                and c.scheduled_at and c.scheduled_at <= now and (now.date() - c.date).days <= RECENT_DAYS]
    for mtg in sorted(meetings, key=lambda c: c.date, reverse=True):
        rid = f"fomc:{mtg.date.isoformat()}"
        if rid in state.releases:
            return None
        before = [o for o in up.observations if o.date <= mtg.date]
        after = [o for o in up.observations if o.date > mtg.date]
        after_lo = [o for o in lo.observations if o.date > mtg.date]
        if not before or not after or not after_lo:
            return None  # FRED not yet updated with the post-meeting range
        prev_u, new_u, new_l = before[-1].value, after[0].value, after_lo[0].value
        move_bp = round((new_u - prev_u) * 100)
        action = "held" if move_bp == 0 else ("raised" if move_bp > 0 else "cut")
        ff = next((c for c in state.calendar.values() if c.indicator_id == "us_fed_upper" and c.date == mtg.date), None)
        rel = EconomicRelease(
            id=rid, indicator_id="us_fed_upper", name="FOMC decision", short="Fed funds target (upper)",
            region="US", topic="monetary_policy", period=mtg.date.isoformat(),
            period_label=mtg.date.strftime("%b %-d, %Y meeting"), units="%", decimals=2,
            actual=new_u, previous=prev_u, previous_label="pre-meeting", detected_at=now, importance="high",
            family="fed", release_time=mtg.scheduled_at, release_time_basis="official_schedule",
            source_name="Federal Reserve via FRED (DFEDTARU/DFEDTARL)",
            source_url="https://www.federalreserve.gov/monetarypolicy/openmarket.htm",
            calendar_key=mtg.key,
            notes=[f"Target range {action}" + (f" by {abs(move_bp)}bp" if move_bp else "") + f" to {new_l:.2f}–{new_u:.2f}%."],
        )
        if ff and ff.consensus:
            c = parse_forecast(ff.consensus, upper_spec)
            if c is not None:
                rel.consensus, rel.consensus_source = c, ff.consensus_source
                rel.surprise, rel.surprise_direction = surprise(new_u, c, 2)
        if rel.consensus is None:
            rel.consensus_note = "No published forecast for the decision found in free sources."
        state.releases[rid] = rel
        mtg.actual, mtg.actual_source, mtg.release_id, mtg.status = f"{new_l:.2f}–{new_u:.2f}%", rel.source_name, rid, "released"
        title = f"FOMC {action} the fed funds target range" + (f" by {abs(move_bp)}bp" if move_bp else "") + f" at {new_l:.2f}–{new_u:.2f}%"
        if move_bp == 0:
            title = f"FOMC held the fed funds target range at {new_l:.2f}–{new_u:.2f}%"
        attach_release(state, rel, title)
        return rel
    return None
