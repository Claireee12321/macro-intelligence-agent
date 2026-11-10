# Implementation Plan

Work proceeds milestone by milestone. **At each checkpoint (CP) work stops for owner review**; the next milestone starts only after the owner confirms or requests changes. Each checkpoint report covers: what was implemented, files changed, tests run (pass/fail), what remains incomplete, commit/push status, and actions needed from the owner.

| Milestone | Checkpoint after it |
|---|---|
| M0 Audit & baseline | **CP0** — review audit, architecture and plan before code restructuring |
| M1 Stabilize data pipeline + M2 Macro-first logic | **CP1** — review real collected data, source mix, clustering, scoring, analysis schema/output |
| M3 Website MVP | **CP2** — review the local site on desktop & mobile |
| M4 Automation | **CP3** — review scheduled runs, reliability, Actions minutes, LLM cost |
| M5 Deployment prep | **CP4** — explicit approval before anything is deployed or any account/billing is set up |

---

## M0 — Repository audit & baseline ✅ (CP0 approved 2026-11-05)

- Clone baseline, tag `marketbrief-baseline`, disable pushes to upstream remote.
- Reproducible dev environment (Python 3.12 venv; Node 20; conda env used on this machine because Xcode CLT is broken).
- `docs/AUDIT.md`, `PRODUCT_SPEC.md`, `ARCHITECTURE.md`, this plan, `PROGRESS.md`, `AGENTS.md`.
- Private GitHub repo with `main` = untouched baseline, `dev` = all new work.

**Acceptance:** confirmed defects documented with evidence; plan reviewed at CP0.

## M1 — Stabilize the data pipeline ✅

- Rename package to `macro_intel` (history-preserving), remove Telegram/Feishu/MCP/crypto/ETF/unused deps; keep MIT notice.
- Typed models (`models.py`), JSON `Store` with atomic writes and pruning.
- News ingestion: stable IDs (canonical-URL hash), publication + collection timestamps, `updated_parsed` fallback, short attributed summaries, per-feed error isolation, deterministic selection.
- Dedup (URL/title exact) + event clustering (concept tags + title similarity + time window), wired into the pipeline.
- Market fetch fixes: yields in bp, explicit source + as-of on every quote, ECB fix only as labeled fallback.
- `macro-intel run --no-llm` produces structured state + export JSON.
- Tests: normalization, IDs, dedup/clustering, store, market change semantics.

**Acceptance:** two consecutive runs do not duplicate items; same-event articles from different outlets cluster; all items carry source/URL/timestamps; tests pass offline.

## M2 — Macro-first logic ✅ (CP1 reviewed 2026-11-05; feedback applied)

- Macro source registry (official sources tier 1; quality media tier 2); drop crypto/AI/DOJ/SEC feeds.
- Topic/region classification and deterministic relevance + event importance scoring (breadth bonus is logarithmic and capped).
- Indicator catalog (inflation, labor, growth, policy, rates, credit, financial conditions, fiscal/liquidity, secondary regions) from FRED/Treasury/NY Fed with units, periods, changes, derived spreads, first-seen vintage log.
- Calendar: Forex Factory (persisted forecasts), FOMC schedule, BEA schedule, FRED release dates (if key). Consensus always source-labeled; never previous-as-consensus.
- Release detection: new official prints → `EconomicRelease` with actual/consensus/previous/surprise.
- Observed market reaction per event (window + timestamps).
- Deterministic `MacroState` (growth, inflation, policy, financial conditions) with evidence.
- LLM stage 1 (EventAnalysis) and stage 2 (DailyBriefing), schema-validated, budget-capped; deterministic data-only briefing. (Owner: build but do not run against a paid API yet.)
- Tests: scoring, consensus parsing/matching, release detection, transforms, regime rules, LLM schema validation & budget guard (fake provider), selection logic (no re-analysis of unchanged events).

**Acceptance:** live run yields a macro-dominated event list, correct releases/surprises against labeled consensus, a regime summary with evidence; LLM path validated with a fake provider and (if a key is provided) one real low-cost run.

→ **CP1**

## M3 — Website MVP ✅ (CP2 approved 2026-11-07)

- `web/` React + TS + Vite + Tailwind; reads export JSON.
- Pages: Overview (narrative, regime, top developments, key markets, next events), Events (chronological, filters, detail with labeled FACT / CONSENSUS / AI / OBSERVED sections), Calendar, Markets dashboard, Briefings, Sources & methodology.
- Freshness/last-update everywhere; stale badges; sample-data banner when applicable.
- Mobile responsive; fast (no heavy chart libs unless needed).

**Acceptance:** `npm run build` passes type-check; site renders real exported data locally on desktop & mobile widths.

→ **CP2**

## M4 — Automate updates ✅ (live on `main` 2026-11-07; pending CP3 review)

- `.github/workflows/update.yml`: cron **once per weekday at 10:05 ET** (owner decision 2026-11-05; dual UTC crons 14:05/15:05 + ET-time guard for DST), manual dispatch, `concurrency` lock, pip/npm caching, `data` branch persistence with retry-on-conflict push, failure summaries.
- Run log, stage-level failure isolation, idempotent briefings.
- Tests for scheduling-slot logic and failure handling.

**Acceptance:** scheduled runs update the `data` branch unattended for ≥ 1 day; Actions minutes within the free allowance.

→ **CP3**

## M5 — Public showcase + private daily site (revised 2026-11-10)

Owner goals: a **public** repo that shows the agent's workflow and full example output, without sharing data; and a
**private link** to open each day that looks exactly like the local site.

1. **Prepare the public showcase (in the private repo, nothing published):** realistic fictional sample day with
   example AI sections (`macro-intel sample`, `SampleProvider`), sample-mode UI, README for visitors with
   screenshots, demo-site workflow (GitHub Pages, sample only, public repos only), update workflow restricted to
   private repos, personal details removed from docs. → **owner review**
2. **Publish (owner approval required):** rename the current repo to `macro-intelligence-private`; create the public
   `macro-intelligence-agent` from a clean snapshot of the code (no `data` branch, no history containing data);
   enable Pages (demo) and template mode.
3. **Private daily site:** Cloudflare Pages + Cloudflare Access (owner-only login) deployed from the private repo;
   Cloudflare cron trigger at 10:05 ET calling `workflow_dispatch`; private repo tracks code from the public repo.

→ **CP4** after each publish step (owner approval required before anything goes public)

## Later (not now)

Breaking-news alerts, long-term event memory, historical reaction statistics, quantitative forecasting/backtesting, multi-agent reasoning, trade recommendations, portfolio features.
