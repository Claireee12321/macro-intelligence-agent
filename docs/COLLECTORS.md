# Bring your own collectors

This repository contains the **processing, analysis and website** layers of the Macro Intelligence Agent and a
fully synthetic sample day. It deliberately ships **no live data collection**: you choose your sources, read
their terms of use, and implement a small collector class. Everything downstream — deduplication, event
clustering, releases vs consensus, the macro regime, observed reactions, optional AI analysis and the website —
works unchanged.

## The contract

Implement the four methods of `macro_intel.collect.Collectors` ([src/macro_intel/collect.py](../src/macro_intel/collect.py)):

| Method | Returns | Used for |
|---|---|---|
| `fetch_news(sources, timeout)` | `(list[NewsItem], list[SourceResult])` | headlines → events, ranking, attribution |
| `update_series(series, requests, api_key)` | `{series_id: error}` (fills `series` in place) | indicators, releases, regime |
| `update_calendar(state, settings)` | `{source: count}` or `{source: "error: …"}` (upserts `state.calendar`) | consensus, "coming up", Today block |
| `market_snapshot(specs, series)` | `MarketSnapshot` | markets dashboard, US stock block, observed reactions |

Then run with `MACRO_COLLECTORS=your_module:YourCollectors macro-intel run`.

**[`macro_intel.sample.SampleCollectors`](../src/macro_intel/sample.py) is a complete, working reference
implementation** (synthetic data, no network) — start by copying it.

## What each piece must contain

- **`NewsItem`** — `id` (stable, e.g. hash of the canonical URL; `macro_intel.process.text.canonical_url` and
  `stable_id` help), `source_id` matching a `config/sources.json` entry, `title`, `url`, `published_at` (UTC),
  `collected_at`, and an optional short `summary`. Store excerpts, never full articles.
- **`SeriesData`** — `observations` as `(date, value)` for the series ids requested (ids follow FRED naming,
  as listed in `config/indicators.json`, which defines transforms, units and release tracking). Set
  `latest_realtime_start` / `initial_release` if your source provides vintages (first prints vs revisions).
- **`CalendarEvent`** — `title`, `country`, `date`/`scheduled_at`, `importance`, optional `family`/`indicator_id`
  (match `calendar_patterns` in `config/indicators.json`). Put a **published forecast** in `consensus` with its
  `consensus_source`; never put the previous value there; leave `actual` empty (it is filled from official data).
- **`MarketQuote`** — `value`, `prev_value`, `change` (use `macro_intel.process.quotes.compute_change` for bp/%
  semantics), `as_of`, `as_of_label`, `kind` (`intraday` / `eod` / `daily_fix`), `source`, and `history`
  (`(ISO date, value)` pairs) for sparklines and reaction windows. Instrument ids come from `config/markets.json`.

## Good practice

- Isolate failures per source (return a failed `SourceResult` or an error string); the pipeline records health.
- Add timeouts, retries with backoff and modest request rates (`macro_intel.http.get` does this).
- Keep collected data in a **private** repository or storage if it includes licensed third-party content.
- Label delayed or unofficial data honestly in `source` and `as_of_label`.
