// Shapes of the JSON bundle written by macro_intel/publish/export.py.

export type Iso = string

export interface SourceHealth {
  ok?: boolean
  last_attempt?: Iso
  last_ok?: Iso
  fetched?: number
  error?: string
}

export interface StageResult {
  name: string
  status: 'ok' | 'error' | 'skipped'
  duration_s: number
  detail: string
  counts: Record<string, number>
}

export interface RunRecord {
  id: string
  started_at: Iso
  finished_at: Iso | null
  trigger: string
  mode: string
  stages: StageResult[]
  llm_calls: number
  llm_cost_usd: number
  ok: boolean
}

export interface Meta {
  app: string
  version: string
  generated_at: Iso
  is_sample: boolean
  mode: 'ai' | 'data-only' | 'sample'
  schedule: string
  last_run: RunRecord | null
  llm: { enabled: boolean; provider: string; model: string | null; calls_today: number; cost_today_usd: number; daily_budget_usd: number }
  fred_api: boolean
  source_health: Record<string, SourceHealth>
  market_source_status: Record<string, string>
  stale_site_after_hours: number
}

export interface Quote {
  id: string
  label: string
  group: string
  value: number | null
  units: '%' | 'bp' | 'index' | 'price' | 'fx'
  decimals: number
  change: number | null
  change_units: 'bp' | '%' | 'pts'
  prev_value: number | null
  prev_label: string
  as_of: Iso | null
  as_of_label: string
  kind: 'intraday' | 'eod' | 'daily_fix' | 'derived'
  source: string
  source_url: string
  stale: boolean
  history: [string, number][]
  note: string
}

export interface Release {
  id: string
  indicator_id: string
  name: string
  short: string
  region: string
  topic: string
  period: string
  period_label: string
  units: string
  decimals: number
  actual: number
  previous: number | null
  previous_label: string | null
  consensus: number | null
  consensus_source: string | null
  consensus_note: string
  surprise: number | null
  surprise_direction: 'above' | 'below' | 'in_line' | null
  release_time: Iso | null
  release_time_basis: string
  detected_at: Iso
  vintage_note: string
  source_name: string
  source_url: string
  importance: 'high' | 'medium' | 'low'
  family: string | null
  event_id: string | null
  notes: string[]
  actual_display: string | null
  previous_display: string | null
  consensus_display: string | null
  previous_first_print_display: string | null
  surprise_display?: string
}

export interface NewsItem {
  id: string
  source_id: string
  source_name: string
  source_kind: 'official' | 'media' | 'research'
  url: string
  title: string
  summary: string
  published_at: Iso | null
  published_estimated: boolean
  collected_at: Iso
  relevance: number
}

export interface MarketImpact {
  asset: string
  instrument: string
  direction: string
  strength: 'weak' | 'moderate' | 'strong'
  confidence: 'low' | 'medium' | 'high'
  horizon: string
  mechanism: string
}

export interface EventAnalysis {
  headline: string
  summary: string
  facts: { text: string; refs: string[] }[]
  expectations: string
  economic_interpretation: { dimension: string; assessment: string; reasoning: string }[]
  narrative_effect: string
  narrative_explanation: string
  market_impacts: MarketImpact[]
  alternative_scenarios: { scenario: string; implications: string }[]
  reaction_consistency: string
  reaction_explanation: string
  watch_next: string[]
  invalidation_triggers: string[]
  key_uncertainties: string[]
}

export interface AnalysisRecord {
  event_id: string
  generated_at: Iso
  provider: string
  model: string
  prompt_version: string
  output: EventAnalysis
  dropped_refs: string[]
}

export interface ObservedMove {
  instrument_id: string
  label: string
  start_value: number | null
  end_value: number | null
  change: number | null
  change_units: 'bp' | '%' | 'pts'
  start_label: string
  end_label: string
  source: string
}

export interface ObservedReaction {
  window: string
  measured_at: Iso
  final: boolean
  moves: ObservedMove[]
  caveats: string[]
}

export interface EventCard {
  id: string
  kind: 'news' | 'data_release'
  title: string
  region: string
  topics: string[]
  importance: number
  importance_reasons: string[]
  first_published_at: Iso | null
  last_published_at: Iso | null
  first_seen_at: Iso
  updated_at: Iso
  source_count: number
  has_official_source: boolean
  analysis_status: string
  summary: string
  lead_source: string
  lead_url: string
  released_at?: Iso | null
}

export interface EventFull extends EventCard {
  items: NewsItem[]
  releases: Release[]
  analysis: AnalysisRecord | null
  observed_reaction: ObservedReaction | null
}

export interface CalendarLine {
  title: string
  consensus: string | null
  consensus_source: string | null
  previous: string | null
  previous_source?: string | null
  actual: string | null
  actual_source: string | null
  release_id?: string | null
  scheduled_at?: Iso | null
}

export interface CalendarRow {
  key: string
  date: string
  scheduled_at: Iso | null
  all_day: boolean
  country: string
  region: string
  family: string | null
  title: string
  importance: 'high' | 'medium' | 'low'
  status: 'upcoming' | 'released' | 'past'
  lines: CalendarLine[]
  sources: string[]
  url: string
}

export interface RegimeEvidence {
  indicator: string
  display: string
  as_of: string
  signal: number
  weight: number
  rule: string
}

export interface RegimeDimension {
  dimension: 'growth' | 'inflation' | 'monetary_policy' | 'financial_conditions'
  state: string
  score: number | null
  evidence: RegimeEvidence[]
  data_gaps: string[]
  as_of: string | null
  method: string
}

export interface MacroState {
  generated_at: Iso
  dimensions: RegimeDimension[]
  summary: string
}

export interface EquitySummary {
  generated_at: Iso
  session: 'pre_open' | 'intraday' | 'closed' | 'unknown'
  session_label: string
  indices: { id: string; label: string; value: number | null; change_pct: number | null; as_of_label: string }[]
  vix: number | null
  vix_change: number | null
  breadth_note: string
  sentiment: string
  sentiment_rule: string
  headlines: { title: string; source_name: string; url: string; published_at: Iso | null }[]
  summary: string
}

export interface BriefingPoint {
  text: string
  event_ids: string[]
}

export interface Briefing {
  id: string
  date: string
  slot: string
  generated_at: Iso
  mode: 'ai' | 'data_only'
  provider: string | null
  model: string | null
  content: {
    headline: string
    overview: string
    us_equity_market: string
    key_developments: BriefingPoint[]
    what_changed: string
    market_implications: BriefingPoint[]
    what_to_watch: BriefingPoint[]
    risks: string[]
  }
  data_points: string[]
  equities: EquitySummary | null
  event_ids: string[]
}

export interface PolicyDecision {
  family: string
  bank: string
  name: string
  date: string
  scheduled_at: Iso
  status: 'done' | 'later today'
  lines: CalendarLine[]
  outcome: { text: string; source: string; release_id: string } | null
  coverage: { event_id: string; title: string; sources: number } | null
}

export interface Overview {
  generated_at: Iso
  today: { central_bank_decisions: PolicyDecision[]; key_releases: Release[]; us_equities: EquitySummary | null }
  macro_state: MacroState | null
  briefing: Briefing | null
  top_events: EventCard[]
  key_markets: Quote[]
  upcoming: CalendarRow[]
  recent_releases: Release[]
  today_date: string
}

export interface IndicatorReading {
  id: string
  name: string
  short: string
  topic: string
  region: string
  units: string
  frequency: string
  decimals: number
  latest: number | null
  latest_period: string | null
  latest_label: string
  latest_display: string
  released?: string | null
  previous: number | null
  previous_label: string
  previous_display: string
  change: number | null
  change_units: string
  history: [string, number][]
  source: string
  source_url: string
  fetched_at: Iso | null
  vintage: string
  stale: boolean
  stale_reason: string
  notes: string
}

export interface SourceInfo {
  id: string
  name: string
  url: string
  homepage: string
  kind: string
  tier: number
  region: string
  paywalled: boolean
  health: SourceHealth | null
}

export interface Bundle {
  meta: Meta
  overview: Overview
  events: { generated_at: Iso; events: EventFull[] }
  calendar: { generated_at: Iso; rows: CalendarRow[] }
  markets: { generated_at: Iso; snapshot_taken_at: Iso | null; groups: { id: string; label: string; quotes: Quote[] }[]; source_status: Record<string, string> }
  economy: { generated_at: Iso; groups: { id: string; label: string; indicators: IndicatorReading[] }[] }
  briefings: { generated_at: Iso; briefings: Briefing[] }
  sources: { generated_at: Iso; sources: SourceInfo[] }
}
