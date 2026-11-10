import json
from datetime import timedelta

from macro_intel.analysis import interpret
from macro_intel.analysis.briefing import make_briefing
from macro_intel.analysis.llm import Budget, call_structured
from macro_intel.models import (
    BriefingDraft,
    EventAnalysis,
    FactStatement,
    LLMCall,
    LLMUsage,
    MarketImpact,
)
from macro_intel.process.cluster import assign_events, ingest_items
from macro_intel.process.regime import assess
from macro_intel.sample import SampleCollectors, sample_series
from macro_intel.store import State, Store

from .conftest import NOW, SRC, make_item


class FakeProvider:
    name = "fake"
    model = "claude-opus-5-5"

    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail

    def generate(self, system, user, schema, max_tokens=16000):
        self.calls += 1
        if self.fail:
            raise RuntimeError("boom")
        usage = LLMUsage(input_tokens=2000, output_tokens=1500, cost_usd=0.038)
        if schema is EventAnalysis:
            return EventAnalysis(
                headline="h", summary="s", facts=[FactStatement(text="f", refs=["I1", "X9"])], expectations="none",
                economic_interpretation=[], narrative_effect="unclear", narrative_explanation="",
                market_impacts=[MarketImpact(asset="front_end_rates", direction="up", strength="moderate",
                                             confidence="medium", horizon="days", mechanism="m")],
                alternative_scenarios=[], reaction_consistency="insufficient_data", reaction_explanation="",
                watch_next=[], invalidation_triggers=[], key_uncertainties=[]), usage
        return BriefingDraft(headline="AI", overview="o", key_developments=[], what_changed="", market_implications=[],
                             what_to_watch=[], risks=[]), usage


def _state_with_event():
    st = State()
    new = ingest_items(st, [make_item("off", "Consumer Price Index rises 0.4% in October", -2),
                            make_item("wire", "US consumer prices rise more than expected as core CPI firms", -1)], SRC)
    assign_events(st, new)
    return st


def test_budget_blocks_calls_over_cap(settings):
    st = State()
    settings.llm_max_calls_per_day = 1
    st.llm_calls.append(LLMCall(at=NOW, purpose="x", provider="fake", model="claude-opus-5-5", cost_usd=0.01))
    parsed, usage, err = call_structured(FakeProvider(), Budget(st, settings), "t", "sys", "user", BriefingDraft)
    assert parsed is None and err.startswith("budget")
    settings.llm_max_calls_per_day = 10
    settings.llm_daily_budget_usd = 0.0105
    assert call_structured(FakeProvider(), Budget(st, settings), "t", "sys", "user", BriefingDraft)[0] is None


def test_provider_failure_is_contained(settings):
    st = State()
    parsed, _, err = call_structured(FakeProvider(fail=True), Budget(st, settings), "t", "s", "u", BriefingDraft)
    assert parsed is None and "boom" in err and st.llm_calls[-1].ok is False


def test_event_analysis_runs_once_and_maps_refs(settings):
    st = _state_with_event()
    settings.llm_min_importance = 50
    prov = FakeProvider()
    c1 = interpret.run_event_analyses(st, settings, prov)
    assert c1["analyzed"] == 1
    ev = next(e for e in st.events.values() if e.analysis)
    assert ev.analysis.dropped_refs == ["X9"]  # invented ref removed
    assert ev.analysis.output.facts[0].refs[0] in st.items  # short ref mapped to real id
    # Unchanged event → no second paid call.
    c2 = interpret.run_event_analyses(st, settings, prov)
    assert c2["candidates"] == 0 and prov.calls == 1


def test_material_change_triggers_reanalysis_after_cooldown(settings, frozen_now):
    from macro_intel import timeutil

    st = _state_with_event()
    settings.llm_min_importance = 50
    prov = FakeProvider()
    interpret.run_event_analyses(st, settings, prov)
    ev = next(e for e in st.events.values() if e.analysis)
    new = ingest_items(st, [make_item("off", "Consumer Price Index detailed tables released for October CPI", 0.5)], SRC)
    assign_events(st, new)
    assert ev.id == new[0].event_id
    assert not interpret.needs_analysis(st, ev, settings)  # within cooldown
    timeutil.set_now(NOW + timedelta(hours=13))
    assert interpret.needs_analysis(st, ev, settings)


def test_data_only_mode_marks_events_and_makes_deterministic_briefing(settings):
    st = _state_with_event()
    settings.llm_min_importance = 50
    counts = interpret.run_event_analyses(st, settings, None)
    assert counts["analyzed"] == 0
    assert any(e.analysis_status == "skipped_no_llm" for e in st.events.values())
    b = make_briefing(st, settings, None)
    assert b.mode == "data_only" and "AI interpretation is disabled" in b.content.overview
    assert make_briefing(st, settings, None) is None  # idempotent per day
    b2 = make_briefing(st, settings, FakeProvider())  # upgrade to AI when a provider appears
    assert b2 is not None and b2.mode == "ai"


def test_regime_on_sample_series(settings):
    ms = assess(settings.indicators, sample_series(settings, NOW))
    assert {d.dimension for d in ms.dimensions} == {"growth", "inflation", "monetary_policy", "financial_conditions"}
    for d in ms.dimensions:
        assert d.state and (d.evidence or d.data_gaps)


def test_end_to_end_offline_cycle_is_idempotent(settings):
    from macro_intel.pipeline import run_cycle
    from macro_intel.sample import SAMPLE_SOURCES

    settings.sources = list(SAMPLE_SOURCES)
    run1 = run_cycle(settings, trigger="test", collectors=SampleCollectors(settings, NOW))
    run2 = run_cycle(settings, trigger="test", collectors=SampleCollectors(settings, NOW))
    assert run1.ok and run2.ok, [s for s in run1.stages + run2.stages if s.status == "error"]
    st = Store(settings.state_dir).load()
    assert len(st.runs) == 2
    news2 = next(s for s in run2.stages if s.name == "news")
    assert news2.counts["new_items"] == 0
    site = settings.site_dir
    for f in ("meta.json", "overview.json", "events.json", "calendar.json", "markets.json", "economy.json",
              "briefings.json", "sources.json"):
        assert (site / f).exists(), f
    meta = json.loads((site / "meta.json").read_text())
    assert meta["is_sample"] is False and meta["mode"] == "data-only"
    events = json.loads((site / "events.json").read_text())["events"]
    assert events and all(e["items"] or e["releases"] for e in events)
    for e in events:
        for it in e["items"]:
            assert it["url"] and it["source_name"] and it["collected_at"]


def test_schedule_gate_handles_dst_and_duplicates():
    from datetime import datetime, timezone

    from macro_intel.schedule import should_run

    utc = timezone.utc

    def run(started, ok=True, finished=True, trigger="schedule"):
        return {"trigger": trigger, "started_at": started.isoformat(), "ok": ok,
                "finished_at": started.isoformat() if finished else None}

    # Winter (EST): 14:08 UTC = 09:08 ET → skip; 15:08 UTC = 10:08 ET → run.
    assert should_run([], datetime(2026, 11, 9, 14, 8, tzinfo=utc), "schedule")[0] is False
    assert should_run([], datetime(2026, 11, 9, 15, 8, tzinfo=utc), "schedule")[0] is True
    # A late firing (e.g. 18:19 ET) runs if nothing succeeded yet; the next one then skips.
    first = run(datetime(2026, 11, 9, 23, 19, tzinfo=utc))
    assert should_run([], datetime(2026, 11, 9, 23, 19, tzinfo=utc), "schedule")[0] is True
    assert should_run([first], datetime(2026, 11, 9, 23, 45, tzinfo=utc), "schedule")[0] is False
    # Failed or unfinished runs do not block a backup firing.
    assert should_run([run(datetime(2026, 6, 8, 14, 8, tzinfo=utc), ok=False)], datetime(2026, 6, 8, 14, 38, tzinfo=utc), "schedule")[0] is True
    assert should_run([run(datetime(2026, 6, 8, 14, 8, tzinfo=utc), finished=False)], datetime(2026, 6, 8, 14, 38, tzinfo=utc), "schedule")[0] is True
    # A manual run earlier that day does not count as the scheduled update.
    assert should_run([run(datetime(2026, 11, 10, 18, 4, tzinfo=utc), trigger="workflow_dispatch")], datetime(2026, 11, 10, 19, 8, tzinfo=utc), "schedule")[0] is True
    # Weekend skips; manual runs always pass.
    assert should_run([], datetime(2026, 11, 7, 15, 8, tzinfo=utc), "schedule")[0] is False
    assert should_run([first], datetime(2026, 11, 9, 23, 45, tzinfo=utc), "workflow_dispatch")[0] is True


def test_saved_run_record_counts_as_success_for_the_gate(settings):
    from macro_intel.pipeline import run_cycle
    from macro_intel.sample import SAMPLE_SOURCES
    from macro_intel.schedule import load_runs, succeeded

    settings.sources = list(SAMPLE_SOURCES)
    run_cycle(settings, trigger="schedule", collectors=SampleCollectors(settings, NOW))
    runs = load_runs(settings.state_dir / "runs.json")
    assert runs and succeeded(runs[-1])
    assert any(s["name"] == "export" and s["status"] == "ok" for s in runs[-1]["stages"])


def test_run_without_collectors_explains_how_to_add_them(settings, monkeypatch):
    import pytest

    from macro_intel.pipeline import NoCollectorsError, run_cycle

    monkeypatch.setattr("macro_intel.pipeline.load_collectors", lambda: None)
    with pytest.raises(NoCollectorsError, match="COLLECTORS"):
        run_cycle(settings)


def test_sample_collectors_satisfy_the_protocol(settings):
    from macro_intel.collect import Collectors

    c: Collectors = SampleCollectors(settings, NOW)
    items, results = c.fetch_news([], 5)
    assert items and all(i.title.startswith("[SAMPLE]") for i in items) and all(r.ok for r in results)
