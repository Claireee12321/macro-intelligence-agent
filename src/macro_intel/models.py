"""Domain models for every structure flowing through the pipeline.

Provenance is encoded in the types themselves:

* facts            -> NewsItem (attributed headline/summary), EconomicRelease.actual, SeriesData
* consensus        -> EconomicRelease.consensus / CalendarEvent.consensus (+ *_source, never inferred)
* model output     -> EventAnalysis / BriefingDraft (only inside AnalysisRecord / DailyBriefing)
* observed markets -> MarketQuote / ObservedReaction (measured data with timestamps)

Models use ``extra="ignore"`` so older state files keep loading after schema additions.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Region = Literal["US", "EA", "UK", "JP", "CN", "CA", "AU", "NZ", "CH", "SE", "NO", "Global", "Other"]
# Coverage: G10 economies + China. "Other" = outside coverage (kept in state, never shown as an event).
REGION_NAMES = {"US": "United States", "EA": "Euro area", "UK": "United Kingdom", "JP": "Japan", "CN": "China",
                "CA": "Canada", "AU": "Australia", "NZ": "New Zealand", "CH": "Switzerland", "SE": "Sweden",
                "NO": "Norway", "Global": "Global", "Other": "Outside coverage"}
SourceKind = Literal["official", "media", "research"]
Importance = Literal["high", "medium", "low"]

TOPICS = (
    "inflation",
    "labor",
    "growth",
    "monetary_policy",
    "fiscal_policy",
    "financial_conditions",
    "rates",
    "fx",
    "energy_commodities",
    "trade_geopolitics",
    "housing",
    "equities",
    "other",
)


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore")


# ── Configuration-backed registries ──────────────────────────────────────────


class NewsSource(_Base):
    """A feed in the source registry (config/sources.json)."""

    id: str
    name: str
    url: str
    homepage: str = ""
    kind: SourceKind = "media"
    tier: int = 2  # 1 = primary/official, 2 = quality media, 3 = other / niche
    region: Region = "US"  # default region for items when text gives no signal
    topics: list[str] = Field(default_factory=list)  # default topic hints
    enabled: bool = True
    max_items: int = 30
    paywalled: bool = False
    notes: str = ""


class IndicatorSpec(_Base):
    """An economic indicator derived from one data series (config/indicators.json)."""

    id: str
    name: str
    short: str
    series_id: str
    source: Literal["fred"] = "fred"
    transform: Literal["level", "pct_mom", "pct_yoy", "diff", "ann_3m"] = "level"
    scale: float = 1.0  # applied to raw values before the transform (e.g. 0.001 -> thousands)
    units: str = ""
    decimals: int = 1
    topic: str = "other"
    region: Region = "US"
    frequency: Literal["D", "W", "M", "Q"] = "M"
    release: bool = False  # track new prints as EconomicRelease
    track_revisions: bool = False  # e.g. GDP advance/second/third estimates on the same period
    importance: Importance = "medium"
    family: Optional[str] = None  # calendar family, e.g. "us_cpi"
    calendar_patterns: list[str] = Field(default_factory=list)  # regexes on calendar titles
    calendar_country: str = "USD"
    source_name: str = ""
    display: bool = True
    stale_after_days: Optional[int] = None  # default derived from frequency
    notes: str = ""


class MarketSpec(_Base):
    """A market instrument on the dashboard (config/markets.json)."""

    id: str
    label: str
    group: str
    source: Literal["yahoo", "treasury", "treasury_real", "nyfed", "fred", "derived", "ecb"]
    symbol: str = ""
    formula: Optional[str] = None  # derived: "a - b" over other quote ids
    scale: float = 1.0  # multiplies source values (e.g. OAS in % → bp)
    units: Literal["%", "bp", "index", "price", "fx"] = "price"
    decimals: int = 2
    change_units: Literal["bp", "%", "pts"] = "%"
    fallback: Optional[str] = None  # id of a quote to use when this one is unavailable
    overview: bool = False
    reaction: bool = False  # include in observed-reaction measurements
    stale_after_hours: float = 30.0
    note: str = ""


# ── News & events ────────────────────────────────────────────────────────────


class NewsItem(_Base):
    id: str  # sha1(canonical_url)[:16]
    source_id: str
    source_name: str
    source_kind: SourceKind = "media"
    source_tier: int = 2
    url: str
    title: str
    summary: str = ""  # short excerpt supplied by the feed, attributed, truncated
    published_at: Optional[datetime] = None
    published_estimated: bool = False  # True when the feed gave no timestamp
    collected_at: datetime
    region: Region = "Other"
    topics: list[str] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)
    relevance: float = 0.0
    relevance_reasons: list[str] = Field(default_factory=list)
    event_id: Optional[str] = None


class ObservedMove(_Base):
    instrument_id: str
    label: str
    start_value: Optional[float] = None
    end_value: Optional[float] = None
    change: Optional[float] = None
    change_units: Literal["bp", "%", "pts"] = "%"
    start_label: str = ""
    end_label: str = ""
    source: str = ""


class ObservedReaction(_Base):
    """Measured market moves over an explicit window — data, not model output."""

    window: str
    measured_at: datetime
    final: bool = False  # True once the window's end is a completed session close
    moves: list[ObservedMove] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


# ── LLM output schemas (what the model returns) ──────────────────────────────

AssetClass = Literal[
    "front_end_rates",
    "long_end_rates",
    "yield_curve",
    "real_yields",
    "breakevens",
    "policy_expectations",
    "usd",
    "fx_other",
    "credit",
    "oil",
    "gold",
    "commodities_other",
    "equities",
    "volatility",
]


class MarketImpact(_Base):
    """Model-generated potential impact. Qualitative by design: no point forecasts."""

    asset: AssetClass
    instrument: str = ""
    direction: Literal[
        "up", "down", "steeper", "flatter", "wider", "tighter", "stronger", "weaker", "mixed", "unclear"
    ]
    strength: Literal["weak", "moderate", "strong"]
    confidence: Literal["low", "medium", "high"]
    horizon: Literal["intraday", "days", "weeks", "months"]
    mechanism: str


class FactStatement(_Base):
    text: str
    refs: list[str] = Field(default_factory=list)  # ids of provided items/releases supporting it


class Interpretation(_Base):
    dimension: Literal[
        "inflation", "growth", "labor", "monetary_policy", "fiscal", "financial_conditions", "global_spillovers"
    ]
    assessment: str
    reasoning: str


class Scenario(_Base):
    scenario: str
    implications: str


class EventAnalysis(_Base):
    """Stage-1 LLM output for one macro event."""

    headline: str
    summary: str
    facts: list[FactStatement]
    expectations: str
    economic_interpretation: list[Interpretation]
    narrative_effect: Literal["reinforces", "challenges", "mixed", "unclear"]
    narrative_explanation: str
    market_impacts: list[MarketImpact]
    alternative_scenarios: list[Scenario]
    reaction_consistency: Literal["consistent", "partly_consistent", "inconsistent", "insufficient_data"]
    reaction_explanation: str
    watch_next: list[str]
    invalidation_triggers: list[str]
    key_uncertainties: list[str]


class BriefingPoint(_Base):
    text: str
    event_ids: list[str] = Field(default_factory=list)


class BriefingDraft(_Base):
    """Stage-2 LLM output (or deterministic data-only equivalent)."""

    headline: str
    overview: str
    us_equity_market: str = ""  # high-level sentiment summary from the supplied index data + headlines
    key_developments: list[BriefingPoint]
    what_changed: str
    market_implications: list[BriefingPoint]
    what_to_watch: list[BriefingPoint]
    risks: list[str]


class LLMUsage(_Base):
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class AnalysisRecord(_Base):
    event_id: str
    generated_at: datetime
    provider: str
    model: str
    prompt_version: str
    input_hash: str
    input_item_ids: list[str] = Field(default_factory=list)
    input_release_ids: list[str] = Field(default_factory=list)
    output: EventAnalysis
    usage: LLMUsage = Field(default_factory=LLMUsage)
    dropped_refs: list[str] = Field(default_factory=list)


class MacroEvent(_Base):
    """A cluster of items (and/or an official release) about one development."""

    id: str
    kind: Literal["news", "data_release"] = "news"
    title: str
    region: Region = "Other"
    topics: list[str] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)
    item_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    has_official_source: bool = False
    first_published_at: Optional[datetime] = None
    last_published_at: Optional[datetime] = None
    first_seen_at: datetime
    updated_at: datetime
    importance: float = 0.0
    importance_reasons: list[str] = Field(default_factory=list)
    release_ids: list[str] = Field(default_factory=list)
    calendar_keys: list[str] = Field(default_factory=list)
    analysis_status: Literal[
        "not_required", "pending", "done", "failed", "skipped_budget", "skipped_no_llm"
    ] = "not_required"
    analysis: Optional[AnalysisRecord] = None
    analysis_attempts: int = 0
    observed_reaction: Optional[ObservedReaction] = None


# ── Economic data ────────────────────────────────────────────────────────────


class Observation(_Base):
    date: date
    value: float


class FirstSeen(_Base):
    value: float
    seen_at: datetime


class SeriesData(_Base):
    """One raw data series. ``first_seen`` is our own real-time vintage log."""

    series_id: str
    source: str = "fred"
    title: str = ""
    units: str = ""
    frequency: str = ""
    observations: list[Observation] = Field(default_factory=list)
    fetched_at: datetime
    source_updated_at: Optional[datetime] = None
    vintage: str = "latest"
    first_seen: dict[str, FirstSeen] = Field(default_factory=dict)
    initial_release: dict[str, float] = Field(default_factory=dict)  # ALFRED first prints (API key only)
    latest_realtime_start: Optional[date] = None  # FRED API: when the latest obs became available


class EconomicRelease(_Base):
    id: str
    indicator_id: str
    name: str
    short: str
    region: Region = "US"
    topic: str = "other"
    period: str
    period_label: str
    units: str = ""
    decimals: int = 1
    actual: float
    previous: Optional[float] = None
    previous_label: Optional[str] = None
    previous_first_print: Optional[float] = None
    consensus: Optional[float] = None
    consensus_source: Optional[str] = None
    consensus_note: str = ""
    surprise: Optional[float] = None
    surprise_direction: Optional[Literal["above", "below", "in_line"]] = None
    release_time: Optional[datetime] = None
    release_time_basis: Literal["calendar", "official_schedule", "fred_realtime", "first_detected"] = "first_detected"
    detected_at: datetime
    vintage_note: str = ""
    source_name: str = ""
    source_url: str = ""
    importance: Importance = "medium"
    family: Optional[str] = None
    calendar_key: Optional[str] = None
    event_id: Optional[str] = None
    notes: list[str] = Field(default_factory=list)


class CalendarEvent(_Base):
    key: str
    title: str
    country: str  # currency-style code from the source: USD, EUR, GBP, JPY, CNY
    region: Region = "Other"
    date: date
    scheduled_at: Optional[datetime] = None
    all_day: bool = False
    importance: Importance = "medium"
    category: str = ""
    family: Optional[str] = None
    indicator_id: Optional[str] = None
    consensus: Optional[str] = None  # as published by the source, verbatim
    consensus_source: Optional[str] = None
    previous: Optional[str] = None  # as published by the source, verbatim
    previous_source: Optional[str] = None
    actual: Optional[str] = None  # only ever filled from official data after release
    actual_source: Optional[str] = None
    release_id: Optional[str] = None
    status: Literal["upcoming", "released", "past"] = "upcoming"
    sources: list[str] = Field(default_factory=list)
    url: str = ""
    first_seen_at: datetime
    updated_at: datetime
    reaction: Optional[ObservedReaction] = None


# ── Markets ──────────────────────────────────────────────────────────────────


class MarketQuote(_Base):
    id: str
    label: str
    group: str
    value: Optional[float] = None
    units: Literal["%", "bp", "index", "price", "fx"] = "price"
    decimals: int = 2
    change: Optional[float] = None
    change_units: Literal["bp", "%", "pts"] = "%"
    prev_value: Optional[float] = None
    prev_label: str = ""
    as_of: Optional[datetime] = None
    as_of_label: str = ""
    kind: Literal["intraday", "eod", "daily_fix", "derived"] = "eod"
    source: str = ""
    source_url: str = ""
    stale: bool = False
    history: list[tuple[str, float]] = Field(default_factory=list)  # (ISO date, close)
    note: str = ""


class MarketSnapshot(_Base):
    taken_at: datetime
    quotes: dict[str, MarketQuote] = Field(default_factory=dict)
    source_status: dict[str, str] = Field(default_factory=dict)


# ── Macro regime ─────────────────────────────────────────────────────────────


class RegimeEvidence(_Base):
    indicator: str
    display: str
    as_of: str = ""
    signal: int = 0  # +1 / 0 / -1 in the dimension's own direction (see rule)
    weight: float = 1.0
    rule: str = ""


class RegimeDimension(_Base):
    dimension: Literal["growth", "inflation", "monetary_policy", "financial_conditions"]
    state: str
    score: Optional[float] = None
    evidence: list[RegimeEvidence] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    as_of: Optional[str] = None
    method: str = ""


class MacroState(_Base):
    generated_at: datetime
    dimensions: list[RegimeDimension] = Field(default_factory=list)
    summary: str = ""


# ── Briefings, runs, usage ───────────────────────────────────────────────────


class IndexMove(_Base):
    id: str
    label: str
    value: Optional[float] = None
    change_pct: Optional[float] = None
    as_of_label: str = ""


class MarketHeadline(_Base):
    title: str
    source_name: str
    url: str
    published_at: Optional[datetime] = None


class EquityMarketSummary(_Base):
    """Deterministic US stock-market snapshot (data + rule-based sentiment gauge + attributed headlines)."""

    generated_at: datetime
    session: Literal["pre_open", "intraday", "closed", "unknown"] = "unknown"
    session_label: str = ""
    indices: list[IndexMove] = Field(default_factory=list)
    vix: Optional[float] = None
    vix_change: Optional[float] = None
    breadth_note: str = ""
    sentiment: Literal["strongly positive", "positive", "mixed / flat", "negative", "strongly negative", "unavailable"] = "unavailable"
    sentiment_rule: str = ""
    headlines: list[MarketHeadline] = Field(default_factory=list)
    summary: str = ""


class DailyBriefing(_Base):
    id: str
    date: date
    slot: str = "daily"
    generated_at: datetime
    mode: Literal["ai", "data_only"]
    provider: Optional[str] = None
    model: Optional[str] = None
    content: BriefingDraft
    data_points: list[str] = Field(default_factory=list)  # deterministic facts from the data layer
    equities: Optional[EquityMarketSummary] = None
    event_ids: list[str] = Field(default_factory=list)
    release_ids: list[str] = Field(default_factory=list)
    usage: LLMUsage = Field(default_factory=LLMUsage)


class StageResult(_Base):
    name: str
    status: Literal["ok", "error", "skipped"]
    duration_s: float = 0.0
    detail: str = ""
    counts: dict[str, int] = Field(default_factory=dict)


class RunRecord(_Base):
    id: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    trigger: str = "manual"
    mode: str = "data-only"
    stages: list[StageResult] = Field(default_factory=list)
    llm_calls: int = 0
    llm_cost_usd: float = 0.0
    ok: bool = True


class LLMCall(_Base):
    at: datetime
    purpose: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    ok: bool = True
    error: str = ""
