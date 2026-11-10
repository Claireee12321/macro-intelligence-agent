# Progress Log

## Current status

**M5 step 1 (public showcase preparation) done — waiting for owner review before anything is published** (2026-11-10). PRs #2 and #3 merged.

Owner decisions so far: architecture approved (CP0); FRED API key to be added; update schedule **once per
weekday at 10:05 ET**; LLM integration built but **not to be run** for now (owner may switch to a
subscription-based backend) — LLM provider defaults to `none`.

## M0 — Repository audit & baseline (2026-11-05) ✅

- Baseline `yukipanpan/marketbrief@cf9b5d0` tagged `marketbrief-baseline`; upstream remote push-disabled.
- Private repo `Claireee12321/macro-intelligence-agent` created; `main` = baseline, `dev` = work.
- Toolchain on the owner's Mac: a dedicated conda env (git, Node 20, gh,
  Python 3.12) because Xcode CLT is broken; project venv `.venv`.
- Docs: AUDIT, PRODUCT_SPEC, ARCHITECTURE, IMPLEMENTATION_PLAN, PROGRESS, AGENTS.md.

## M1 — Stabilize the data pipeline ✅

- Package restructure (`macro_intel`), removal of out-of-scope modules and unused dependencies.
- Typed models, JSON store, HTTP retry helper, news ingestion with stable IDs/timestamps/summaries.
- Dedup + event clustering wired into the pipeline; source attribution on every item.
- Market data fixes (bp changes for yields, labeled sources/as-of, ECB only as fallback).

## M2 — Macro-first logic ✅

- Macro source registry (25 feeds: 9 official tier-1, 16 media/research); crypto/AI/DOJ feeds dropped.
- 46 FRED-based indicators (inflation, labor, growth, policy, financial conditions, liquidity, fiscal, EA).
- 43 market instruments (official Treasury curves, NY Fed rates, FRED credit spreads, delayed quotes).
- Calendar: Forex Factory (persisted forecasts), FOMC and BEA schedules, FRED release calendar (with key).
- Release detection with labeled consensus and surprise; FOMC decision objects; GDP revisions.
- Observed reactions (official-timestamp events only), deterministic regime, AI stages (fake-tested),
  deterministic data-only briefing, site export bundle, `digest` and `sample` commands.

### Live verification (2026-11-05 ~01:50 ET, data-only, no FRED key)

- 25/25 feeds OK, 322 items → 319 new → ~50 macro-relevant, ~28 events ≥ 45 importance.
- 43/43 FRED series, 43/43 market quotes, 81 Forex Factory rows, 10 FOMC meetings, 5 BEA releases.
- A JOLTS release was detected and matched to its published Forex Factory forecast, with the revised previous value.
- Regime produced for all four dimensions with per-rule evidence.
- Second run: 0 new items, no duplicate events/releases, briefing not regenerated (idempotent).

### Tests

`pytest -q` → **39 passed** (offline, ~2 s): normalisation, scoring/regions, dedup/clustering,
release-event attachment, store/prune, transforms, consensus parsing & unit conversion, previous-never-
consensus, bootstrap no-backfill, GDP revisions, change semantics, Treasury CSV, Forex Factory/FOMC/BEA
parsers, regime, LLM budget caps & failure containment, no re-analysis of unchanged events, ref
validation, data-only briefing idempotency, offline end-to-end double run.

### Known problems / open items

See ARCHITECTURE §9. Additionally: ranking weights are first-pass and should be tuned with owner feedback;
BoJ/ECB official items can still rank close to mid-tier US news.

## CP1 feedback round (2026-11-05 afternoon) ✅

Owner feedback → implemented:
1. "Broad USD 121.7" explained (Fed trade-weighted dollar index); relabeled in plain English and its regime rule
   now uses % change (±1.5%). EUR/USD, GBP/USD etc. remain on the FX dashboard.
2. Coverage limited to **G10 + China**; non-US only when material (display policy in ARCHITECTURE §5); EM items
   capped and hidden; Spanish/Portuguese-language headlines filtered; G10 central banks (BoC, RBA, RBNZ, SNB,
   Riksbank, Norges) recognised; calendar filtered accordingly.
3. Overview/briefing now open with **Today**: central-bank decisions → key releases → **US stock market**
   (indices, VIX, breadth, rule-based sentiment, attributed market-wrap headlines). Added Dow, Nasdaq Composite,
   equal-weight S&P (RSP) and the CNBC top-news feed.
Also: market-episode clustering (today's sell-off = one event, 5 sources), speeches no longer promoted to
policy decisions, single-stock stories excluded from market shocks. Tests: **43 passed**.

## FRED API key (2026-11-05) ✅

Owner provided a key; stored only in local `.env` (gitignored). Verified: API path for all 43 series, ALFRED
first prints (first print vs revised previous values visible), FRED release calendar (official dates beyond the
current week). Key format is validated at load. Will be added as a GitHub Actions secret in M4.

## M3 — Website MVP ✅

- `web/` React + TS + Vite + Tailwind; pages Overview, Events (+ detail A–F), Calendar, Markets, Economy,
  Briefings, About; responsive (verified at 390 px and 1280 px), light/dark themes.
- Provenance badges (Fact / Official data / Consensus / AI interpretation / AI potential impact / Observed),
  freshness indicator and stale banner, sample-data banner, per-quote stale badges, sparklines with hover readout.
- Verified by rendering the production build in headless Chrome (desktop, true 390 px mobile via iframe,
  dark mode, event detail, markets). Fixed: grid overflow on mobile (min-w-0), compact as-of labels, release
  table spacing and stacked mobile layout, readable derived-spread labels.
- `npm run build` (tsc type-check + Vite) passes; Python suite 44 passed.

## M4 — Automation (2026-11-07) 🔧

- `.github/workflows/update.yml` (weekdays ~10:05 ET + manual), `macro-intel gate` (DST-aware once-per-day
  gate, `schedule.py`), `macro-intel status --markdown` job summary, self-bootstrapping `data` branch,
  site build + artifact. Dry-run of every workflow command locally on a fresh data dir: OK. Tests: 45 passed.
- Pushing to `main` is refused by this environment's safety check, so `dev` → `main` goes through a PR the
  owner merges (PR #1, merged 2026-11-07 as a merge commit).
- `FRED_API_KEY` added as an encrypted Actions secret (owner-approved); `data` branch seeded from the
  2026-11-05 local state so captured forecasts carry over.
- **Verified on GitHub** (manual run 42409352840, ~60 s): every step green; data committed to `data`; site
  artifact 164 KB; FRED API used; all official sources and Yahoo OK from GitHub IPs (42/42 quotes, none stale).
  The October employment report (released Fri Nov 6) was detected against the seeded Forex Factory
  forecasts (payrolls, unemployment rate, average hourly earnings).
- Known: FXStreet and Calculated Risk return HTTP 403 to GitHub's cloud IPs (they work locally); isolated,
  shown as failed on the About page.

## Incident 2026-11-09/10 — GitHub schedule unreliable

- Mon 2026-11-09: both scheduled firings ran ~8 h late (18:19 and 18:45 ET); the second should have been
  skipped but the gate looked for an `export` stage that was only recorded after state was saved.
- Tue 2026-11-10: no scheduled firing by 13:03 ET, so the 08:30 ET CPI release was missing. Manual refresh
  triggered at 13:04 ET; the CPI release was then included with its published forecast.
- Also found: CPI and core CPI attached to two different pre-existing news events → duplicate CPI event.
- Fixes (PR #2): pipeline records the run before export and saves last; gate counts runs with `finished_at`
  + `ok`; gate is stdlib-only and runs before installation; two weekday firings (10:08 ET + 11:08 ET backup,
  owner: max two); release
  families attach to one event; self-healing merge of duplicate release events. Tests: 47 passed.
- Owner feedback 2026-11-10: (1) max two firings → 10:08 ET + 11:08 ET backup (winter UTC times; DST
  reminder recorded); (2) show when each data release came out → release date/time and age on event cards,
  in a "Released" column of the release table (desktop and mobile), in briefing/digest lines, and the official
  publication date on the Economy page (FRED API). Also fixed: Fed "approval of … applications" items now
  routine; market headlines limited to the last 12 h and ranked by freshness; market-episode titles use the
  latest wrap headline. Self-heal verified on a copy of the real state (2 CPI events → 1, 14 articles).
- Recommendation: an external trigger (e.g. a Cloudflare Worker cron calling `workflow_dispatch`) for reliable
  10:05 ET timing — natural to add in M5 alongside hosting.

## Next steps

Merge PR #2 → observe scheduled runs. **Before 2027-03-08 (DST):** switch crons to `8 14,15` or make the
external 10:05 ET trigger primary.

Then: observe scheduled runs (Mon 2026-11-09 ~10:05 ET) → CP3 review → M5 deployment prep
(Cloudflare Pages + Access; owner approval required before anything is published).

## M5 step 1 — Public showcase preparation (2026-11-10) ✅ (not published)

- Owner decision: public repo `macro-intelligence-agent` (code + docs + sample demo, no data); current repo becomes
  private `macro-intelligence-private` (daily update, data, private site). Names approved.
- Realistic fictional sample day (`sample.py`): CPI release beating labeled forecasts, ECB decision, Fed speech,
  euro-area inflation, US market wraps, synthetic but plausible series/quotes (seeded random walks), rule-based
  regime consistent with the story, canned example AI analyses and briefing (`SampleProvider`, no model call).
  Every element labeled SAMPLE; synthetic numbers are never attributed to real agencies; `macro-intel sample`
  refuses to overwrite a non-sample directory.
- UI: sample banner ("a fictional, synthetic day…"), no stale warning in sample mode.
- README rewritten for public visitors with screenshots (`docs/images/`), live-demo link (active after publishing).
- `.github/workflows/demo.yml` (GitHub Pages, sample only, public repos only); `update.yml` now runs only in
  private repos. Personal path removed from docs; `view-latest.sh` toolchain path made generic.
- Tests: 48 passed; website builds.
