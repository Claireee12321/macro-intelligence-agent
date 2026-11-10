"""Indicator transforms, period labels and dashboard readings (MacroIndicator views)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from macro_intel.models import IndicatorSpec, Observation, SeriesData
from macro_intel.timeutil import utc_now

DEFAULT_STALE_DAYS = {"D": 5, "W": 14, "M": 75, "Q": 150}
HISTORY_POINTS = {"D": 90, "W": 52, "M": 36, "Q": 16}
_YOY_LAG = {"M": 12, "Q": 4, "W": 52}


def _months_between(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month)


def _consecutive(prev: date, cur: date, freq: str, steps: int = 1) -> bool:
    if freq == "M":
        return _months_between(prev, cur) == steps
    if freq == "Q":
        return _months_between(prev, cur) == 3 * steps
    if freq == "W":
        return abs((cur - prev).days - 7 * steps) <= 1
    return True  # daily: business-day gaps are normal


def transform(spec: IndicatorSpec, observations: list[Observation]) -> list[tuple[date, float]]:
    """Apply ``spec.scale`` then ``spec.transform``. Requires truly consecutive periods."""
    vals = [(o.date, o.value * spec.scale) for o in sorted(observations, key=lambda o: o.date)]
    t, freq = spec.transform, spec.frequency
    if t == "level":
        return vals
    out: list[tuple[date, float]] = []
    if t in ("pct_mom", "diff"):
        for (d0, v0), (d1, v1) in zip(vals, vals[1:]):
            if not _consecutive(d0, d1, freq):
                continue
            if t == "diff":
                out.append((d1, v1 - v0))
            elif v0:
                out.append((d1, (v1 / v0 - 1.0) * 100.0))
        return out
    if t == "ann_3m":
        by_date = dict(vals)
        for d1, v1 in vals:
            d0 = _shift_months(d1, -3)
            v0 = by_date.get(d0)
            if v0:
                out.append((d1, ((v1 / v0) ** 4 - 1.0) * 100.0))
        return out
    if t == "pct_yoy":
        lag = _YOY_LAG.get(freq)
        if lag is None:
            return []
        if freq in ("M", "Q"):
            by_date = dict(vals)
            for d1, v1 in vals:
                v0 = by_date.get(_shift_months(d1, -12))
                if v0:
                    out.append((d1, (v1 / v0 - 1.0) * 100.0))
        else:
            for i in range(lag, len(vals)):
                d0, v0 = vals[i - lag]
                d1, v1 = vals[i]
                if v0 and _consecutive(d0, d1, freq, lag):
                    out.append((d1, (v1 / v0 - 1.0) * 100.0))
        return out
    raise ValueError(f"unknown transform {t}")


def _shift_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    return date(d.year + m // 12, m % 12 + 1, 1)


def period_label(d: date, freq: str) -> str:
    if freq == "M":
        return d.strftime("%b %Y")
    if freq == "Q":
        return f"Q{(d.month - 1) // 3 + 1} {d.year}"
    if freq == "W":
        return f"week ending {d.strftime('%b %-d, %Y')}"
    return d.isoformat()


def stale_days(spec: IndicatorSpec) -> int:
    return spec.stale_after_days or DEFAULT_STALE_DAYS.get(spec.frequency, 30)


def change_units(spec: IndicatorSpec) -> str:
    u = spec.units
    if u.startswith("%"):
        return "pp"
    return u


def fmt_value(value: float | None, spec: IndicatorSpec, signed: bool | None = None) -> str:
    if value is None:
        return "n/a"
    if signed is None:
        signed = spec.transform in ("pct_mom", "diff") or (spec.units.startswith("% q/q"))
    s = f"{value:+,.{spec.decimals}f}" if signed else f"{value:,.{spec.decimals}f}"
    u = spec.units
    if u.startswith("%"):
        return f"{s}%"
    if u in ("K", "M"):
        return f"{s}{u}"
    if u.startswith("$"):
        sign = "-" if value < 0 else ("+" if signed and value > 0 else "")
        return f"{sign}${abs(value):,.{spec.decimals}f}{u[1:]}"
    return s


@dataclass
class IndicatorReading:
    id: str
    name: str
    short: str
    topic: str
    region: str
    units: str
    frequency: str
    decimals: int
    latest: float | None = None
    latest_period: str | None = None
    latest_label: str = ""
    latest_display: str = "n/a"
    released: str | None = None  # official publication date of the latest observation (FRED API), if known
    previous: float | None = None
    previous_label: str = ""
    previous_display: str = "n/a"
    change: float | None = None
    change_units: str = ""
    history: list[tuple[str, float]] = field(default_factory=list)
    source: str = ""
    source_url: str = ""
    fetched_at: str | None = None
    vintage: str = ""
    stale: bool = True
    stale_reason: str = "no data"
    notes: str = ""


def reading(spec: IndicatorSpec, series: SeriesData | None) -> IndicatorReading:
    r = IndicatorReading(
        id=spec.id, name=spec.name, short=spec.short, topic=spec.topic, region=spec.region,
        units=spec.units, frequency=spec.frequency, decimals=spec.decimals, notes=spec.notes,
        source=f"{spec.source_name} via FRED" if spec.source_name and "FRED" not in spec.source_name else spec.source_name or "FRED",
        source_url=f"https://fred.stlouisfed.org/series/{spec.series_id}",
        change_units=change_units(spec),
    )
    if series is None or not series.observations:
        return r
    if series.source == "sample":
        r.source, r.source_url = "SAMPLE (synthetic)", ""
    vals = transform(spec, series.observations)
    if not vals:
        r.stale_reason = "insufficient history for transform"
        return r
    d1, v1 = vals[-1]
    r.latest, r.latest_period, r.latest_label = v1, d1.isoformat(), period_label(d1, spec.frequency)
    r.latest_display = fmt_value(v1, spec)
    if len(vals) >= 2:
        d0, v0 = vals[-2]
        r.previous, r.previous_label = v0, period_label(d0, spec.frequency)
        r.previous_display = fmt_value(v0, spec)
        r.change = v1 - v0
    r.history = [(d.isoformat(), round(v, 4)) for d, v in vals[-HISTORY_POINTS.get(spec.frequency, 36):]]
    raw_latest = max(o.date for o in series.observations)
    if series.latest_realtime_start and raw_latest == d1:
        r.released = series.latest_realtime_start.isoformat()
    r.fetched_at = series.fetched_at.isoformat()
    r.vintage = series.vintage
    age = (utc_now().date() - d1).days
    limit = stale_days(spec)
    r.stale = age > limit
    r.stale_reason = f"latest observation {r.latest_label} is {age} days old (threshold {limit})" if r.stale else ""
    return r
