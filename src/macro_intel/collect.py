"""Data collection interface — "bring your own collectors".

The processing, analysis and website layers only need four things from the outside world, described by
the ``Collectors`` protocol below. This repository's public edition ships **no live data collection**:
it includes ``macro_intel.sample.SampleCollectors`` (a fully synthetic day) and expects you to implement
your own collectors for the sources you choose — respecting each source's terms of use.

Point ``MACRO_COLLECTORS`` at your implementation, e.g. ``MACRO_COLLECTORS=my_pkg.collectors:MyCollectors``.
See docs/COLLECTORS.md for the contract and a minimal example.
"""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:  # pragma: no cover
    from macro_intel.config import Settings
    from macro_intel.models import MarketSnapshot, MarketSpec, NewsItem, NewsSource, SeriesData
    from macro_intel.store import State


@dataclass
class SourceResult:
    """Per-source fetch outcome, recorded as source health on the About page."""

    source_id: str
    ok: bool
    fetched: int = 0
    kept: int = 0
    error: str = ""


@dataclass
class SeriesRequest:
    """One economic series the pipeline needs (ids follow FRED conventions, see config/indicators.json)."""

    series_id: str
    frequency: str  # D / W / M / Q
    want_initial: bool  # also return first-release values, if your source has vintages


class Collectors(Protocol):
    """What a data collector must provide. All methods should isolate their own failures."""

    name: str

    def fetch_news(self, sources: list[NewsSource], timeout: float) -> tuple[list[NewsItem], list[SourceResult]]:
        """Recent items for the configured sources (title, link, timestamp, short summary)."""

    def update_series(self, series: dict[str, SeriesData], requests: list[SeriesRequest], api_key: str) -> dict[str, str]:
        """Refresh ``series`` in place; return {series_id: error} for failures."""

    def update_calendar(self, state: State, settings: Settings) -> dict[str, int | str]:
        """Upsert ``CalendarEvent`` rows into ``state.calendar``; return {source: count} or {source: "error: …"}."""

    def market_snapshot(self, specs: list[MarketSpec], series: dict[str, SeriesData]) -> MarketSnapshot:
        """Current quotes for the configured instruments, each with value, change, source and as-of time."""


DEFAULT_LIVE = "macro_intel.ingest.live:LiveCollectors"  # present only in private deployments


def load_collectors(spec: str | None = None) -> Collectors | None:
    """Resolve ``module:Class`` (``MACRO_COLLECTORS`` or the private default). None if not installed."""
    spec = spec or os.environ.get("MACRO_COLLECTORS") or DEFAULT_LIVE
    module, _, cls = spec.partition(":")
    try:
        mod = importlib.import_module(module)
    except ModuleNotFoundError as exc:
        if spec == DEFAULT_LIVE and (exc.name or "").startswith("macro_intel.ingest"):
            return None
        raise
    return getattr(mod, cls)()
