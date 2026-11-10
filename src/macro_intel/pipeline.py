"""One update cycle: collect → process → analyse → store → export.

Every stage is isolated: a failing source or stage is recorded in the run log and the cycle
continues with whatever data is available. State is always saved and the site always exported.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager

from macro_intel.analysis.briefing import make_briefing
from macro_intel.analysis.interpret import run_event_analyses
from macro_intel.analysis.llm import make_provider
from macro_intel.config import Settings
from macro_intel.collect import Collectors, SeriesRequest, load_collectors
from macro_intel.models import RunRecord, StageResult
from macro_intel.process.calendar import refresh_status
from macro_intel.process.cluster import (
    assign_events,
    ingest_items,
    merge_duplicate_release_events,
    refresh_event,
    rescore_items,
)
from macro_intel.process.reaction import update_reactions
from macro_intel.process.regime import assess
from macro_intel.process.releases import detect_releases
from macro_intel.process.scoring import EVENT_DISPLAY_THRESHOLD
from macro_intel.publish.export import build_bundle, write_bundle
from macro_intel.store import State, Store, prune
from macro_intel.timeutil import utc_now

log = logging.getLogger("macro_intel")


class _Stages:
    def __init__(self, run: RunRecord):
        self.run = run

    @contextmanager
    def stage(self, name: str):
        t0 = time.monotonic()
        res = StageResult(name=name, status="ok")
        try:
            yield res
        except Exception as exc:  # isolate stage failures
            log.exception("Stage %s failed", name)
            res.status, res.detail = "error", f"{type(exc).__name__}: {exc}"[:300]
            self.run.ok = False
        finally:
            res.duration_s = round(time.monotonic() - t0, 2)
            self.run.stages.append(res)


class NoCollectorsError(RuntimeError):
    pass


def series_requests(settings: Settings) -> list[SeriesRequest]:
    reqs: dict[str, SeriesRequest] = {}
    for spec in settings.indicators:
        r = reqs.get(spec.series_id)
        want = spec.release or (r.want_initial if r else False)
        reqs[spec.series_id] = SeriesRequest(spec.series_id, spec.frequency, want)
    for m in settings.markets:
        if m.source == "fred" and m.symbol not in reqs:
            reqs[m.symbol] = SeriesRequest(m.symbol, "D", False)
    return list(reqs.values())


def run_cycle(settings: Settings, *, trigger: str = "manual", no_llm: bool = False,
              force_briefing: bool = False, offline_state: State | None = None,
              provider_override=None, collectors: Collectors | None = None) -> RunRecord:
    collectors = collectors or load_collectors()
    if collectors is None:
        raise NoCollectorsError(
            "No data collectors are installed. This edition ships processing, analysis and the website only — "
            "implement macro_intel.collect.Collectors for your own sources and set MACRO_COLLECTORS "
            "(see docs/COLLECTORS.md), or run `macro-intel sample` for the synthetic demo day.")
    store = Store(settings.state_dir)
    state = offline_state if offline_state is not None else store.load()
    provider = provider_override if provider_override is not None else (None if no_llm else make_provider(settings))
    run = RunRecord(id=utc_now().strftime("%Y%m%dT%H%M%SZ"), started_at=utc_now(), trigger=trigger,
                    mode=("ai" if provider else "data-only") + ("" if collectors.name == "live" else f" ({collectors.name})"))
    st = _Stages(run)
    health: dict = state.meta.setdefault("source_health", {})
    new_items = []

    with st.stage("news") as r:
        raw, results = collectors.fetch_news(settings.sources, settings.http_timeout)
        for res in results:
            h = health.setdefault(res.source_id, {})
            h.update(ok=res.ok, last_attempt=utc_now().isoformat(), fetched=res.fetched, error=res.error)
            if res.ok:
                h["last_ok"] = utc_now().isoformat()
        r.counts = {"raw": len(raw), "sources_ok": sum(x.ok for x in results), "sources": len(results)}
        new_items = ingest_items(state, raw, {s.id: s for s in settings.sources})
        r.counts["new_items"] = len(new_items)

    with st.stage("fred") as r:
        errors = collectors.update_series(state.series, series_requests(settings), settings.fred_api_key)
        r.counts = {"series": len(state.series), "errors": len(errors)}
        if errors:
            r.detail = "; ".join(f"{k}: {v}" for k, v in list(errors.items())[:5])

    with st.stage("calendar") as r:
        results_cal = collectors.update_calendar(state, settings)
        counts = {}
        for name, res in results_cal.items():
            h = health.setdefault(f"calendar:{name}", {})
            if isinstance(res, str):
                h.update(ok=False, error=res, last_attempt=utc_now().isoformat())
                r.detail += f"{name}: {res}; "
            else:
                counts[name] = int(res)
                h.update(ok=True, last_ok=utc_now().isoformat(), error="")
        refresh_status(state)
        r.counts = counts

    with st.stage("market") as r:
        snap = collectors.market_snapshot(settings.markets, state.series)
        state.snapshots.append(snap)
        r.counts = {"quotes": sum(1 for q in snap.quotes.values() if q.value is not None), "total": len(snap.quotes)}

    with st.stage("releases") as r:
        new_rel = detect_releases(state, settings.indicators)
        r.counts = {"new_releases": len(new_rel)}

    with st.stage("events") as r:
        rescored = rescore_items(state, {s.id: s for s in settings.sources})
        attached, created = assign_events(state, new_items)
        merged = merge_duplicate_release_events(state)
        for ev in state.events.values():
            refresh_event(state, ev)
        r.counts = {"attached": attached, "created": created, "merged_duplicates": merged, "rescored": rescored,
                    "events": len(state.events)}

    with st.stage("regime") as r:
        state.macro_state = assess(settings.indicators, state.series)

    with st.stage("reactions") as r:
        r.counts = {"measured": update_reactions(list(state.events.values()), state.latest_snapshot,
                                                 settings.markets, EVENT_DISPLAY_THRESHOLD, state.calendar)}

    with st.stage("analysis") as r:
        r.counts = run_event_analyses(state, settings, provider)
        if provider is None:
            r.status, r.detail = "skipped", "LLM disabled (data-only mode)"

    with st.stage("briefing") as r:
        b = make_briefing(state, settings, provider, force=force_briefing)
        r.counts = {"created": 1 if b else 0}
        if b:
            r.detail = f"{b.id} ({b.mode})"

    calls_this_run = [c for c in state.llm_calls if c.at >= run.started_at]
    run.llm_calls = len(calls_this_run)
    run.llm_cost_usd = round(sum(c.cost_usd for c in calls_this_run), 6)

    removed = prune(state)
    run.finished_at = utc_now()
    state.runs.append(run)

    with st.stage("export") as r:
        write_bundle(build_bundle(state, settings), settings.site_dir)

    # Saved last, so the stored run record includes every stage up to and including export.
    with st.stage("store") as r:
        r.counts = removed
        store.save(state)

    log.info("Run %s finished: ok=%s, %s", run.id, run.ok,
             ", ".join(f"{s.name}={s.status}" for s in run.stages))
    return run


def export_only(settings: Settings) -> None:
    state = Store(settings.state_dir).load()
    write_bundle(build_bundle(state, settings), settings.site_dir)
