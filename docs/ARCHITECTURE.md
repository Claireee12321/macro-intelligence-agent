# Architecture

> Status: pipeline (M1–M2), website (M3) and automation workflow (M4) **implemented**; deployment (M5) in progress.
>
> **Public edition note:** the public repository ships the engine and a synthetic sample only. The live collectors
> (`src/macro_intel/ingest/`), the scheduled update workflow and the data live in the author's private deployment;
> they implement the `Collectors` interface (`src/macro_intel/collect.py`, see [COLLECTORS.md](COLLECTORS.md)). Reuse rationale: [AUDIT.md](AUDIT.md).

## 1. Overview

```
 GitHub Actions (weekdays ~10:05 ET + manual; concurrency-locked) — .github/workflows/update.yml
        │
        ▼  macro-intel run
 ┌─────────────── collect (each source isolated) ───────────────┐
 │ RSS: 9 official + 16 media/research feeds  (ingest/news.py)  │
 │ FRED: 46 series, CSV w/o key / API+ALFRED w/ key (fred.py)   │
 │ US Treasury par & real curves, NY Fed EFFR/SOFR,             │
 │ Yahoo (delayed), ECB fix fallback          (market.py)       │
 │ Forex Factory week, FOMC page, BEA page, FRED release dates  │
 │                                             (calendar.py)    │
 └──────────────────────────────────────────────────────────────┘
        │
        ▼  process (deterministic)
 dedup → classify (concepts/topic/region) → relevance score → releases (actual vs labeled
 consensus) → cluster into MacroEvents → event importance → deterministic MacroState →
 observed reactions (official-timestamp events only)
        │
        ▼  analyse (optional, budget-capped; OFF by default)
 stage 1 EventAnalysis (new/materially changed events ≥ importance 60)
 stage 2 DailyBriefing (AI, or deterministic data-only)
        │
        ▼
 data/state/*.json (system of record)  →  data/site/*.json (website bundle)  →  React site (M3)
```

One cycle takes ~6–10 s plus any LLM time. Every stage is wrapped so a failure is logged in the run
record and the cycle continues; state is always saved and the site always exported.

## 2. Key decisions

| Decision | Choice | Why |
|---|---|---|
| Backend | Python ≥ 3.11 package `macro_intel` (renamed from `marketbrief` with history-preserving moves) | Reuse working fetchers; single language. |
| Storage | JSON files in `data/state/` behind `Store` (atomic writes, retention pruning) | Diff-friendly, transparent, portable; swap to SQLite/Postgres later by replacing `Store`. |
| CI persistence (M4) | Orphan `data` branch checked out into `data/` | No external DB; full audit trail; code branches stay clean. |
| Frontend (M3) | Static React + TS + Vite + Tailwind reading `data/site/*.json` | Fast, no server, Cloudflare Pages compatible. |
| Hosting (M5) | Cloudflare Pages + Cloudflare Access | Free tier with real access control. Needs owner approval. |
| LLM | Provider interface; Anthropic structured outputs (`messages.parse` + pydantic); optional OpenAI-compatible; default `none` | Cost control, schema validation, swappable backend. |
| Market data | Official EOD first (Treasury, NY Fed, FRED); Yahoo only for delayed intraday quotes, always labeled | Accuracy & honest provenance. |

## 3. Modules

| Module | Responsibility |
|---|---|
| `config.py` | `Settings` from env + `config/{sources,indicators,markets}.json` |
| `models.py` | All pydantic models (see §4) |
| `store.py` | `State` container, `Store` load/save, `prune` retention |
| `http.py` | Thread-local sessions, timeouts, retry with backoff (no retry on permanent 4xx) |
| `collect.py` | `Collectors` interface (bring your own), `SourceResult`, `SeriesRequest`, `load_collectors` |
| `ingest/live.py` *(private)* | `LiveCollectors` wiring the fetchers below |
| `ingest/news.py` *(private)* | RSS fetch/parse → `NewsItem` (canonical-URL id, UTC times, ≤320-char attributed summary) |
| `ingest/fred.py` *(private)* | FRED CSV/API, ALFRED initial releases, release dates, first-seen vintage log |
| `ingest/market.py` *(private)* | Treasury/NY Fed/FRED/Yahoo/ECB → `MarketSnapshot`; bp semantics; derived spreads; labeled fallbacks |
| `ingest/calendar.py` *(private)* | Forex Factory (persisted), FOMC & BEA schedules, FRED release calendar; throttling |
| `process/text.py` | Canonical URLs, stable ids, tokenisation (stemming + macro synonyms), Jaccard |
| `process/classify.py` | Concept regexes (decision vs mention, release families), topic, region, noise, routine-official |
| `process/scoring.py` | Item relevance and event importance (0–100) with human-readable reasons |
| `process/cluster.py` | Dedup, incremental clustering, release-event attachment, event refresh |
| `process/indicators.py` | Transforms (level, m/m, y/y, diff, 3m ann.), labels, staleness, readings |
| `process/releases.py` | New-print detection, consensus parsing/matching, surprise, GDP revisions, FOMC decisions |
| `process/reaction.py` | Observed market reaction windows |
| `process/regime.py` | Deterministic regime (§6) |
| `process/today.py` | "Today" block: central-bank decisions (last 24 h / later today) with forecast/previous, outcome and coverage; key releases |
| `process/equities.py` | US stock-market snapshot: S&P 500, Dow, Nasdaq Composite, Russell 2000, VIX, equal-weight breadth, rule-based sentiment gauge, attributed market-wrap headlines |
| `analysis/llm.py` | Providers, pricing, `Budget`, `call_structured` (never raises) |
| `analysis/prompts.py` | Versioned system prompts encoding the analytical rules |
| `analysis/context.py` | Deterministic context blocks (markets, regime, calendar) for prompts |
| `analysis/interpret.py` | Stage 1 selection, packet building, ref mapping/validation |
| `analysis/briefing.py` | Stage 2 AI briefing or deterministic data-only briefing (idempotent per day) |
| `publish/export.py` | Site bundle: `meta, overview, events, calendar, markets, economy, briefings, sources` |
| `publish/digest.py` | Markdown digest of the bundle (`macro-intel digest`) |
| `pipeline.py` | Stage orchestration and run record |
| `sample.py` | `SampleCollectors` + `SampleProvider`: the labeled synthetic demo day (reference collector implementation; test fixture) |

## 4. Domain model and provenance

| Content type | Model / field | UI label (M3) |
|---|---|---|
| Fact (news) | `NewsItem` title/summary/url/published_at, attributed to source | FACT · source |
| Fact (data) | `EconomicRelease.actual/previous`, `SeriesData` | OFFICIAL DATA · agency via FRED |
| Consensus | `EconomicRelease.consensus` + `consensus_source`, or `consensus_note` when unavailable | CONSENSUS · Forex Factory forecast |
| Model interpretation | `AnalysisRecord.output` (`EventAnalysis`), `DailyBriefing` (mode `ai`) | AI INTERPRETATION · model, time |
| Model potential impact | `EventAnalysis.market_impacts[]` (`MarketImpact`: direction/strength/confidence/horizon/mechanism) | AI POTENTIAL IMPACT |
| Observed markets | `MarketQuote`, `ObservedReaction` (window, start/end labels, source) | OBSERVED · source, as-of |

Rules enforced in code: consensus only from a matched published forecast (never "previous");
`actual` on calendar rows only from official data; LLM facts must cite provided ref ids (unknown refs
are dropped and recorded in `dropped_refs`); numbers shown as data come from the data layer.

## 5. Scoring, dedup and clustering

* **Item relevance** = (65 × macro_core + tier points 15/10/5 + 10 if a high-impact concept spans several
  macro topics) × region multiplier (0.55 + 0.45 × weight; US 1.0, Global 0.75, EA/CN 0.5, JP 0.45, UK 0.4,
  Other 0.2) − 40 for noise patterns − 40 for routine official publications. macro_core =
  max(topic weight × concept strength) with summary-only concepts at half weight.
* **Dedup**: same canonical-URL id, or same source + same normalized title.
* **Clustering** (items with relevance ≥ 35, 72 h candidate window): shared *specific* family (cpi, pce,
  us_payrolls, fed, ecb, boe, boj, …) + same region + ≤ 36 h + Jaccard ≥ 0.05; shared broad concept +
  ≤ 24 h + Jaccard ≥ 0.30; or near-duplicate headline (Jaccard ≥ 0.5, ≤ 48 h). Official data-release events
  absorb same-family, same-region coverage within 36 h. Same official source merges only near-identical
  titles or meeting outputs published within 3 h of each other.
* **Event importance** = max(item relevance, release base 85/70/55) + coverage breadth min(10, 5·log2 n) +
  5 official source + 5 consensus surprise. LLM threshold 60.
* **Coverage & display policy** (`scoring.display_ok`): US events ≥ 45; Global ≥ 50 with a high-strength concept
  or ≥ 2 sources; Euro area/UK/Japan/China ≥ 55 with a high-strength concept (decision, top-tier release, market
  shock, leadership change) or ≥ 3 sources; other G10 (CA, AU, NZ, CH, SE, NO) ≥ 55 with a high-strength concept
  only; other countries are capped at relevance 15 and never shown. Calendar: US high+medium; EA/UK/JP/CN high;
  other G10 central-bank decisions only.
* **Market episodes**: `market_shock` items (index/bond/FX "plunge/rout/worst day…", single-company stories
  excluded) cluster within 12 h of the episode's first item regardless of wording; the title prefers a market wrap.

## 6. Regime methodology (MVP)

Weighted vote of explicit rules; score ∈ [−1, 1]; > 0.33 / < −0.33 cut-offs; ≥ 3 indicators required.

| Dimension | Rules (signal +1 / −1) |
|---|---|
| Growth | Payrolls 3m vs 12m avg (±25K); unemployment Sahm-style (+0.30pp → slowing); real GDP vs prior-4Q avg (±0.75pp); IP 3m/3m ann. (±2%, w 0.5); real PCE 3m/3m ann. (>3% / <1%); claims 4wk vs 26wk (+10% / −5%, w 0.5) |
| Inflation | Core CPI 3m ann. − y/y (±0.4pp); core PCE same; headline CPI & PPI same (w 0.5); 5y breakeven 1m change (±15bp, w 0.5); UMich 1y 3m change (±0.3pp, w 0.5) |
| Monetary policy | Target change within 120 days → tightening/easing; else real policy rate (EFFR − core PCE y/y): > 1pp restrictive, < 0 accommodative, else neutral; 2Y − EFFR shown as context |
| Financial conditions | NFCI 4wk change (±0.10); HY OAS 1m (+50 / −40bp); IG OAS 1m (+15 / −10bp, w 0.5); trade-weighted USD (Fed broad index vs 26 currencies) 1m change (±1.5%, w 0.5); 10y real yield 1m (±25bp, w 0.5); VIX level (>25 / <15, w 0.5) |

Limitations: US only; thresholds are heuristic (not estimated); uses latest-vintage data for the current
assessment; monthly data lag 2–6 weeks.

## 7. Real-time integrity

* `SeriesData.first_seen` records, per period, the value and time we first observed it — starting empty on
  the first fetch (we did not observe history in real time and do not pretend to).
* With `FRED_API_KEY`, ALFRED initial-release values provide first prints and publication dates.
* Releases record which vintage supplied actual/previous; previous is labeled as including revisions.
* The `data` branch history (M4) is a point-in-time archive of everything shown.

## 8. Cost control and automation

* Items keyed by canonical-URL hash: unchanged stories are never reprocessed.
* Stage 1 runs only for events ≥ 60 importance, published in the last 48 h, never analysed — or with a
  material change (new official release, new official item, or ≥ 3 new items) after a 12 h cooldown;
  ≤ 6 per run; failed events retried at most twice.
* `Budget`: ≤ 20 calls and ≤ $1.00 per ET day by default (pre-call estimate + logged actual cost).
* Briefing idempotent per (ET date, slot); upgraded from data-only to AI once if a provider appears.
* Forex Factory ≤ 1 fetch / 50 min; FOMC/BEA/FRED schedules ≤ 1 / day.
* Schedule (owner decision 2026-11-05): **once per weekday at 10:05 ET** (GitHub cron is approximate; jobs
  often start a few minutes late) to conserve the GitHub Actions allowance.
* Workflow (`.github/workflows/update.yml`): two weekday firings, 15:08 and 16:08 UTC = 10:08 ET normal +
  11:08 ET backup in winter (owner decision 2026-11-10: max two). **DST reminder:** from 2027-03-08 these land
  at 11:08/12:08 EDT — switch to `8 14,15` or make an external 10:05 ET trigger primary. GitHub's scheduler
  proved unreliable (2026-11-09: firings ~8 h late; 2026-11-10: none by 13:00 ET). A stdlib-only gate (`schedule.py`, run with the runner's
  `python3` before anything is installed) passes the first firing at/after 09:55 ET on a weekday and skips the
  backup once a scheduled run has succeeded that day (`finished_at` set and `ok`); a skipped firing costs ~1
  billed minute. Manual dispatch always runs. `concurrency: macro-update` prevents
  overlapping runs. The `data` branch is cloned into `data/` (created on first run), the pipeline runs with
  `MACRO_DATA_DIR=data`, results are committed by `macro-intel-bot` with a 3-attempt rebase/push loop, the
  site is built (`npm ci && npm run build`) and uploaded as the `site` artifact (7-day retention), and the job
  summary shows the stage table (`macro-intel status --markdown`). The pipeline records the run before export
  and saves state last, so the stored run includes the export result. A total failure fails the job, which
  triggers GitHub's standard failed-workflow email to the repo owner.

## 9. Known limitations

* Free consensus = Forex Factory weekly forecasts only (captured while the week is live).
* BLS blocks automated access; BLS data arrives via FRED (usually within ~1 h of release).
* No free reliable intraday 2Y yield; the 2Y T-note futures price is shown as a proxy (price up = yield down).
* ISM PMI actuals are not available from free official sources (calendar shows forecast/previous only).
* With one run per day at 10:05 ET: the US stock-market block shows the previous close plus the first ~35 min
  of trading; 10:00 ET releases may not be in FRED yet; FOMC decisions (2 pm ET) appear the next morning;
  observed reactions for same-day events are provisional until the session closes.
* Classification and clustering are heuristic; occasional over/under-merging is possible.
* `yfinance` is unofficial and may be rate-limited from cloud IPs (quotes then show as unavailable/stale).
* The LLM stage has been validated with a fake provider and schema checks only; no real API call yet.

## 10. Website (M3, implemented)

* `web/`: React 19 + TypeScript + Vite + Tailwind 4; no router or chart library (hash routes, inline SVG).
* Data: fetches `data/*.json` relative to the page (`base: './'`). Dev server serves `../data/site` (or
  `MACRO_SITE_DIR`); `npm run build` copies the bundle into `dist/data`, so `dist/` is a self-contained static site.
* Routes: `#/` overview · `#/events` · `#/events/<id>` · `#/calendar` · `#/markets` · `#/economy` · `#/briefings` · `#/about`.
* Overview order (owner): Today (central-bank decisions → key releases → US stock market) → briefing → top
  developments; side column: regime tiles (with evidence), key markets, coming up.
* Event detail follows the analytical spine A–F (what happened / expected / economic meaning / potential impact /
  observed reaction / what next), each section labeled with its provenance; AI sections show an explicit
  "not available — data-only mode" state.
* Visual system: dataviz reference palette as CSS roles with separately selected dark-mode steps; provenance
  badges use categorical slots 1–3 (validated all-pairs in both modes) plus neutral gray, always with text;
  status colors only for fresh/stale/failed with icon + label; market and regime directions are not colored
  good/bad. Sparklines: 2px line in de-emphasis ink, accent end-dot with surface ring, crosshair readout on hover
  and keyboard, aria summary. Freshness in the header; a banner when data is older than 30 h; a banner for sample data.
