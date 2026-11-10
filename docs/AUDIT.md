# MarketBrief Baseline Audit (Milestone 0)

Audited: `yukipanpan/marketbrief@cf9b5d0` (tagged `marketbrief-baseline` in this repo), 2026-11-05.
Method: full read of all source files plus live execution of the fetchers in data-only mode.

## 1. What the baseline actually is

~1,900 lines of Python (excluding README/prompts). One CLI (`marketbrief generate|fetch|push`) that runs:

```
fetch (market, news, calendar in parallel) → [optional] Claude preflight → Claude report → print JSON / summary
```

| Area | Files | Status |
|---|---|---|
| CLI / orchestration | `__main__.py`, `core/pipeline.py` | Works for `stdout`/`json`. `html`/`pdf`/`markdown` fall back to JSON (`TODO`). |
| Config | `core/config.py` | Works. Loads `config/*.json` or `*.example.json`, `.env`. |
| Types | `core/types.py` | Pydantic models defined but **mostly unused** — pipeline passes raw dicts; `ReportData` never validates LLM output. |
| News | `fetchers/news.py` | RSS fetch works. Dedup exists but is **not wired**. |
| Market | `fetchers/market.py` | Yahoo Finance (yfinance) + Frankfurter (ECB) + Stooq fallback. Works, with labeling bugs. |
| Calendar | `fetchers/calendar.py` | Forex Factory weekly JSON + MyFXBook RSS, **today only**. |
| FRED | `fetchers/fred.py` | 9 series, latest value only. **Not used by the pipeline** (only `fetch fred`). Release-calendar function is never called. |
| Crypto / ETF flows | `fetchers/crypto.py`, `fetchers/etf_flows.py` | CoinGecko / SoSoValue. Not used by the pipeline. Out of scope for macro. |
| AI analysis | `core/analysis.py`, `config/prompts/*` | Two Claude calls (preflight memo → report JSON). Free-form JSON with fence stripping; no schema validation. |
| Delivery | `delivery/telegram.py`, `delivery/feishu.py` | **Stubs** — log "not yet implemented". |
| Renderers | `renderers/__init__.py` | **Empty package.** |
| Cache | `cache/__init__.py` | **Empty package.** No persistence of any kind. |
| MCP server / Claude skill | `mcp_server/`, `claude_skill/` | Thin wrappers over fetchers. Not relevant to a website product. |
| Tests | — | **None.** |
| Automation | `workflows/morning_report.yml.template` | Template only; its Telegram step would "succeed" while doing nothing. |

## 2. Confirmed defects (verified by running the code)

Live run on 2026-11-05 (data-only mode):

1. **Source attribution is broken in the AI pipeline.** `run_report()` builds the citation index from `item["sources"]`, but `fetch_news()` returns items with `source`/`url` only. Measured: 0 of 115 items had `sources` → the source index sent to Claude is empty, so every `[S#]` citation is unresolvable.
2. **Deduplication is not wired into the pipeline.** `dedup_news_items()` is never called. When called manually it merged only 1 cluster out of 115 items (an identical CNBC story appearing twice); title-Jaccard ≥ 0.55 almost never matches different outlets' headlines for the same event. No event clustering exists.
3. **Content is not macro-focused.** Measured mix: 39 markets, 32 crypto, 29 AI/tech blogs, 5 news, 4 China, 4 macro, 2 government. Feeds include DOJ, SEC, NVIDIA/OpenAI blogs, crypto outlets, Tasnim. Keyword filter is crude (`"ai"`, `"rate"` substrings).
4. **Non-deterministic selection.** `random.sample()` picks 20 "wildcard" items each run.
5. **Rates reported as percent change.** The US 10Y change was reported as a percent of the yield (≈ −1.2%) rather than in basis points (≈ −6bp). Misleading for the most important asset class in this project.
6. **FX mislabeling / staleness.** `USD/CNH` falls back to ECB **CNY** reference rate with `high = low = close`; ECB daily fixes (Frankfurter) *overwrite* intraday Yahoo quotes for all FX pairs, without the output saying so.
7. **Stooq fallback change is open→close**, while Yahoo change is close→close — inconsistent semantics. (Stooq 10Y symbol also returns 404 now.)
8. **FRED integration is minimal and disconnected:** 9 series, latest value only — no units, previous values, changes or vintages; not used in the report. `fetch_fred_calendar` exists but is never called. (Its use of `realtime_start/end` to bound release dates matches FRED's documented behaviour — an earlier draft of this audit wrongly flagged it.)
9. **Calendar loses information:** only today's events; `forecast`/`previous` fetched from Forex Factory are discarded before reaching Claude (`time | name | impact` only); `CalendarEvent` model has no forecast/previous fields; no actuals; `date.today()` uses the machine's local timezone; MyFXBook impact parsed by `"high" in description`.
10. **No structured-output validation.** LLM JSON is `json.loads`'d after stripping fences; `ReportData` is never applied. On parse failure it retries the *same* prompt.
11. **Prompt philosophy conflicts with this product.** The baseline prompt demands "assertive, no hedging", "every directional claim needs a number", OW/UW positioning tables, "minimum 8 calendar events", and "status: released if known from news" — these encourage false precision and invented calendar entries/actuals.
12. **No persistence / incremental processing.** Every run re-fetches and (with AI) re-analyzes everything; no record of what was already analyzed → repeated LLM cost.
13. **Delivery and rendering are stubs** (Telegram, Feishu, HTML, PDF, Markdown).
14. **Heavy unused dependencies:** matplotlib, numpy, openpyxl, pillow.
15. **Dead/blocked sources:** WSJ RSS feeds last updated ~1.8 years ago; Treasury press RSS 404; White House feed 404; BLS RSS/ICS return 403 to automated clients.

The "previous review" claims (dedup not wired, Telegram incomplete, limited FRED, incomplete HTML renderer) are **all confirmed**.

## 3. Source reachability probe (2026-11-05)

Working: Federal Reserve RSS (press, monetary, speeches), BEA RSS, Census economic indicators RSS, EIA, ECB press/blog, BoE news, BoJ what's new, CNBC (economy/finance/bonds/world), MarketWatch, Bloomberg (markets/economics headline RSS), FT (global economy/markets headline RSS), Investing.com, FXStreet, BBC Business, NYT Economy, Guardian Economics, SCMP Economy, Econbrowser.
Data endpoints working without keys: Forex Factory weekly calendar JSON (this week only), FRED `fredgraph.csv`, US Treasury daily par & real yield CSV, NY Fed EFFR/SOFR API, Treasury FiscalData API, Fed FOMC calendar page, BEA release schedule page, Frankfurter (ECB), Yahoo Finance via `yfinance` (raw Yahoo API returned 429).
Blocked/dead: BLS (403), WSJ (stale), Treasury press RSS (404), White House (404), Stooq 10Y (404), Forex Factory next-week JSON (404).

## 4. Reuse decisions

| Component | Decision |
|---|---|
| RSS fetching (`fetch_rss_feed`), feed registry concept, spam filtering | **Reuse**, extended with summaries, `updated_parsed` fallback, stable IDs, canonical URLs. |
| Title normalization / Jaccard helpers | **Reuse** inside a new clustering module (with concept tags + time window). |
| Yahoo Finance batch fetch, Frankfurter FX | **Reuse** with bp changes for yields, explicit source/as-of labels, ECB as fallback rather than override. |
| Forex Factory calendar parser | **Reuse**, extended to the full week, with persistence of forecasts and consensus labeling. |
| FRED fetcher, retry helper, `.env`/config loading | **Reuse** and expand (CSV fallback without key, metadata, transforms, vintages when keyed). |
| Two-stage Claude design | **Keep the idea** (per-event interpretation → daily briefing) but rewrite prompts and use schema-validated structured output. |
| Telegram / Feishu / MCP / Claude skill / crypto / ETF flows / MyFXBook | **Remove** from the product (remain available in the `marketbrief-baseline` tag). |
| Renderers / cache stubs | **Replace** with JSON state store + static website. |
