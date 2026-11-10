# Macro Intelligence Agent — Product Specification

Owner: Claireee12321 (private, personal use). Derived from MarketBrief (MIT) but an independent application.

## 1. Vision

A **personal macroeconomic intelligence website** that automatically gathers macro news, economic data, policy developments and market data, and uses AI to interpret their economic and cross-asset implications. It is the owner's primary daily place to understand:

1. What important macro developments occurred?
2. Why do they matter economically?
3. What was expected beforehand?
4. What changed in the economic outlook?
5. Likely implications for monetary policy, rates, FX and other assets?
6. How did markets actually react?
7. What releases/policy events come next?

The **website is the product**. No Telegram/email/messaging as the primary delivery. Updates run automatically without the owner's laptop: every 30–60 min during active market hours plus morning and evening briefings. No tick-level streaming. Must work on desktop and mobile.

## 2. Content priorities

This is a **macroeconomics** product — not a stock picker or investing chatbot.

Highest priority: inflation (CPI, PCE, PPI, expectations); labor (payrolls, unemployment, wages, claims, JOLTS); growth (GDP, retail sales, production, spending, PMIs); monetary policy (Fed decisions, speeches, minutes, guidance); fiscal policy (deficits, spending, Treasury issuance); financial conditions, liquidity, credit; geopolitics/trade/energy with economic consequences.

Geography (owner decision 2026-11-05): **US first; coverage limited to G10 economies + China.** Non-US economies appear only when something material happens there — a central-bank decision, a top-tier data release, a big market move, or a major multi-outlet story. No per-country filler. Other countries (EM) are out of scope for now.

Market-implication priority: (1) UST yields & rate expectations, (2) curve (2s10s, 5s30s), (3) real yields, breakevens, policy expectations, (4) USD & major FX, (5) credit spreads & financial conditions, (6) oil, gold, macro commodities, (7) broad equity indices & macro-sensitive sectors. Equities: broad implications and cross-asset confirmation only.

## 3. Analytical philosophy

For each important event answer:

- **A. What happened?** Verified facts, numbers, source, timestamp.
- **B. What was expected?** Consensus (if available), previous, surprise. State explicitly when reliable consensus is unavailable.
- **C. What does it mean economically?** Inflation/growth/employment/policy/financial-conditions implications; change to the narrative; reinforces or contradicts the regime.
- **D. Potential market impact.** Transmission to rates, curve, FX, credit, commodities, equities — direction, relative strength, confidence, horizon, mechanism; alternative scenarios.
- **E. What markets actually did.** Observed moves with timestamps; expected-vs-observed differences and possible explanations.
- **F. What to monitor next.** Upcoming releases, key uncertainties, invalidation triggers.

**Strict separation** (and visible labeling) of: (1) verified facts, (2) published consensus, (3) model-generated interpretation, (4) model-generated potential impact, (5) observed market movements.

Never invent consensus, prices, dates, news or historical data. No false precision ("10Y +8bp") without an estimated quantitative model. No unsupported confidence percentages. Tone: thoughtful macro research, not a trading-signal service.

## 4. Data requirements

Primary sources: Federal Reserve, FRED, BLS, BEA, US Treasury, Census, EIA, ECB, BoE, other central banks. Secondary: legally accessible news feeds (RSS/official APIs). No scraping of paywalled content; store only links, titles and short attributed summaries.

Each news item retains: unique ID, source & original URL, title, publication timestamp, collection timestamp, region, economic topic, relevance score, analysis status. Deduplicate and cluster articles about the same development; do not overweight stories merely because many outlets cover them.

Economic data: observation value & units, observation period, release date, revision/vintage info (where available), previous observations, changes over relevant periods, derived indicators (e.g. spreads). Respect frequencies; avoid look-ahead bias — revised data must not be presented as what markets saw in real time.

Economic calendar: actual, consensus, previous, timestamp, importance, subsequent market reaction. Never label previous as consensus; never assume actuals before publication.

## 5. AI analysis

Simple structured pipeline: ingestion → normalization → deduplication → macro relevance ranking → event identification → economic context → AI interpretation → market impact assessment → structured storage → website. One or two LLM stages; no gratuitous multi-agent orchestration. Configurable LLM provider (Claude by default; OpenAI-compatible optional). Schema-validated structured outputs.

Core entities: MacroEvent, EconomicRelease, MacroIndicator, MacroState, MarketSnapshot, MarketImpact, NewsSource, DailyBriefing.

## 6. Macro regime

Separate dimensions with supporting data and timestamps:
- Growth: accelerating / stable / slowing
- Inflation: accelerating / stable / cooling
- Monetary policy: tightening / restrictive / easing (plus neutral)
- Financial conditions: tightening / neutral / easing

Deterministic indicators first; LLM explains the evidence. Document limitations.

## 7. Website (MVP sections)

1. **Macro overview** — opens with *Today*: (a) central-bank decisions/meetings (last 24 h or later today) and key data releases, then (b) a high-level **US stock market** point (main indices, VIX, breadth, sentiment, attributed market-wrap headlines — no single-stock commentary); followed by the current narrative and latest significant changes.
2. **Latest news & events** — chronological, source, timestamp, summary, importance; expandable deeper interpretation.
3. **Economic impact analysis** — transmission to rates/FX/credit/commodities/equities with uncertainty and alternatives.
4. **Economic calendar** — upcoming releases and central-bank events.
5. **Macro market dashboard** — UST 2Y/5Y/10Y/30Y, curve spreads, USD & major FX, inflation expectations, credit spreads, oil & gold, SPX/Nasdaq (secondary).
6. **Daily macro briefing** — morning and end-of-day.

Design: clear hierarchy, clean, professional, mobile responsive, fast; source attribution on every item; data freshness and last-update times; stale data explicitly flagged; **no mock data that could be mistaken for live data** (sample data must be clearly labeled).

## 8. Automation & hosting

Scheduled job (GitHub Actions for MVP) that fetches, detects new developments, dedups/prioritizes, runs AI only where needed, stores structured output, and updates the site data. Avoid paying repeatedly for unchanged stories; safeguards for cost, retries, rate limits, duplicate jobs, failures. Hosting candidate: Cloudflare Pages with access control (a private GitHub repo does not make a deployed site private). **No public deployment or paid services without explicit approval.**

## 9. Non-goals for now

High-frequency alerts, long-term event memory, historical reaction statistics, quantitative forecasting/backtesting, advanced multi-agent reasoning, personalized trade recommendations, portfolio management.

## 10. MVP definition of done

1. Runs reliably with documented setup. 2. Collects real macro news and economic data. 3. Dedups and prioritizes new developments. 4. Important events get evidence-backed interpretations. 5. Potential impacts displayed separately from observed reactions. 6. Working responsive webpage. 7. Source links and freshness timestamps visible. 8. Scheduled automatic updates. 9. Core tests pass. 10. Repo private; no credentials exposed. A data-only mode works without an LLM key; sample/fixture data is clearly labeled.
