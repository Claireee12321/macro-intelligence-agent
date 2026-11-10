"""Time helpers. All stored timestamps are timezone-aware UTC; display uses US/Eastern."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
UTC = timezone.utc

_now_override: datetime | None = None


def utc_now() -> datetime:
    """Current UTC time (overridable in tests via ``set_now``)."""
    return _now_override if _now_override is not None else datetime.now(UTC)


def set_now(value: datetime | None) -> None:
    global _now_override
    _now_override = value


def et_now() -> datetime:
    return utc_now().astimezone(ET)


def et_today() -> date:
    return et_now().date()


def to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def et_datetime(d: date, hh: int, mm: int) -> datetime:
    """A wall-clock time in New York on date ``d``, returned in UTC."""
    return datetime.combine(d, time(hh, mm), tzinfo=ET).astimezone(UTC)


def fmt_et(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return dt.astimezone(ET).strftime("%Y-%m-%d %H:%M ET")


def hours_since(dt: datetime | None) -> float | None:
    if dt is None:
        return None
    return (utc_now() - to_utc(dt)).total_seconds() / 3600.0


def previous_weekday(d: date) -> date:
    d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def fmt_release(dt: datetime | None) -> str:
    """Release timestamp for text: 'Tue Nov 10, 08:30 ET' (absolute — text may be read days later)."""
    if dt is None:
        return "release time unknown"
    return dt.astimezone(ET).strftime("%a %b %-d, %H:%M ET")
