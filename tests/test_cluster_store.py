from datetime import timedelta

from macro_intel.models import EconomicRelease
from macro_intel.process.cluster import assign_events, attach_release, ingest_items
from macro_intel.store import State, Store, prune

from .conftest import NOW, SRC, make_item


def _run(state, items):
    new = ingest_items(state, items, SRC)
    assign_events(state, new)
    return new


def test_exact_duplicates_are_dropped_across_runs():
    st = State()
    a = make_item("wire", "US consumer prices rise more than expected in October", url="https://w/1?utm_source=rss")
    same_url = make_item("wire", "US consumer prices rise more than expected in October (updated)", url="http://www.w/1")
    assert len(_run(st, [a])) == 1
    # Same canonical URL → same id → skipped; same source + same title → skipped.
    assert len(_run(st, [same_url, make_item("wire", "US consumer prices rise more than expected in October", url="https://w/2")])) == 0


def test_cross_outlet_cpi_coverage_clusters_into_one_event():
    st = State()
    _run(st, [
        make_item("off", "Consumer Price Index rises 0.4% in October", -3),
        make_item("wire", "US consumer prices rise more than expected as core CPI firms", -2.5),
        make_item("daily", "Hotter US CPI print revives bets on another Fed rate hike", -2),
    ])
    cpi_events = [e for e in st.events.values() if "cpi" in e.concepts]
    assert len(cpi_events) == 1
    ev = cpi_events[0]
    assert len(ev.item_ids) == 3 and len(ev.source_ids) == 3 and ev.has_official_source
    # Breadth bonus is logarithmic and capped.
    assert any("distinct sources" in r for r in ev.importance_reasons)


def test_no_merge_across_regions_or_unrelated_topics():
    st = State()
    _run(st, [
        make_item("wire", "US consumer prices rise more than expected in October", -2),
        make_item("daily", "Euro zone CPI flash estimate hits 4% as ECB hike looms", -2),
        make_item("wire", "Oil falls as OPEC+ signals output increase", -1),
    ])
    assert len(st.events) == 3


def test_same_official_source_distinct_releases_stay_separate():
    st = State()
    _run(st, [
        make_item("ecb", "ECB President Lagarde to step down in February", -30),
        make_item("ecb", "Results of the ECB Survey of Professional Forecasters", -29),
    ])
    assert len(st.events) == 2


def test_release_event_absorbs_same_family_news():
    st = State()
    rel = EconomicRelease(id="us_jolts:2026-09-01", indicator_id="us_jolts", name="JOLTS job openings", short="JOLTS",
                          period="2026-09-01", period_label="Sep 2026", actual=7.52, detected_at=NOW,
                          release_time=NOW - timedelta(hours=3), family="jolts", topic="labor")
    st.releases[rel.id] = rel
    ev = attach_release(st, rel, "US JOLTS (Sep 2026): 7.52M")
    _run(st, [make_item("wire", "Job openings posted big September gain", -1)])
    assert len(st.events) == 1 and len(ev.item_ids) == 1 and ev.kind == "data_release"


def test_store_roundtrip_and_prune(tmp_path):
    st = State()
    _run(st, [make_item("wire", "US consumer prices rise more than expected in October", -1),
              make_item("wire", "Old jobs report story about payrolls", -24 * 30)])
    store = Store(tmp_path / "state")
    store.save(st)
    loaded = store.load()
    assert set(loaded.items) == set(st.items) and set(loaded.events) == set(st.events)
    removed = prune(loaded)
    assert removed["items"] == 1  # 30-day-old item beyond 14-day retention


def test_reactions_only_for_officially_timestamped_events():
    from macro_intel.models import MacroEvent
    from macro_intel.process.reaction import anchor_time

    news = MacroEvent(id="n", title="Oil falls on peace hopes", concepts=["oil"], first_published_at=NOW,
                      first_seen_at=NOW, updated_at=NOW)
    rel = MacroEvent(id="r", kind="data_release", title="CPI", concepts=["cpi"], first_published_at=NOW,
                     first_seen_at=NOW, updated_at=NOW)
    assert anchor_time(news, {}) is None
    assert anchor_time(rel, {}) == NOW


def test_euro_area_inflation_stories_cluster_but_not_with_us_cpi():
    st = State()
    _run(st, [
        make_item("daily", "Euro zone inflation hits 4% for first time in three years", -3),
        make_item("wire", "October inflation in the Eurozone keeps ECB on course for another tightening", -2),
        make_item("wire", "US consumer prices rise more than expected as core CPI firms", -1),
    ])
    regions = sorted(e.region for e in st.events.values())
    assert regions == ["EA", "US"]


def test_non_us_display_policy():
    from macro_intel.models import MacroEvent
    from macro_intel.process.scoring import display_ok

    def ev(region, concepts, imp, sources=("a",)):
        return MacroEvent(id="e", title="t", region=region, concepts=concepts, importance=imp,
                          source_ids=list(sources), first_seen_at=NOW, updated_at=NOW)
    assert display_ok(ev("US", ["adp"], 50))
    assert not display_ok(ev("EA", ["ecb", "wages"], 61))            # routine ECB item: not material
    assert display_ok(ev("EA", ["ecb_policy"], 67))                   # ECB decision
    assert display_ok(ev("UK", ["boe"], 60, ("a", "b", "c")))          # big multi-outlet story
    assert not display_ok(ev("AU", ["rba"], 60, ("a", "b", "c")))      # minor G10 needs a decision/top-tier item
    assert display_ok(ev("AU", ["rba_policy"], 56))
    assert not display_ok(ev("Other", ["gdp"], 90))                    # outside coverage (G10 + China)


def test_out_of_coverage_items_are_capped():
    from macro_intel.models import NewsSource
    from macro_intel.process.classify import classify
    from macro_intel.process.scoring import score_item

    src = NewsSource(id="w", name="W", url="u", region="Global")
    it = make_item("wire", "Indonesian Rupiah gains as Q3 GDP beats expectations")
    score, reasons = score_item(it, classify(it.title, "", src))
    assert score <= 15 and any("outside coverage" in r for r in reasons)


def test_release_family_attaches_to_one_event_even_with_existing_news():
    from macro_intel.models import EconomicRelease
    from macro_intel.process.cluster import merge_duplicate_release_events

    st = State()
    _run(st, [make_item("wire", "US consumer prices expected to rise in October CPI report", -5),
              make_item("daily", "What to expect from today's US inflation reading", -4)])
    rels = []
    for rid, short in (("us_cpi_mom:2026-10-01", "CPI m/m"), ("us_core_cpi_mom:2026-10-01", "Core CPI m/m")):
        r = EconomicRelease(id=rid, indicator_id=rid.split(":")[0], name=short, short=short, period="2026-10-01",
                            period_label="Oct 2026", actual=0.4, detected_at=NOW, release_time=NOW - timedelta(hours=1),
                            family="cpi", topic="inflation")
        st.releases[r.id] = r
        rels.append(r)
    ev = attach_release(st, rels[0], "US CPI (Oct 2026)")
    attach_release(st, rels[1], "US CPI (Oct 2026)", event=ev)
    assert sum(1 for e in st.events.values() if e.kind == "data_release") == 1
    assert set(ev.release_ids) == {r.id for r in rels}
    # Self-heal: two pre-existing duplicate release events get merged.
    from macro_intel.models import MacroEvent
    dup = MacroEvent(id="dup", kind="data_release", title="US CPI (Oct 2026)", region="US", concepts=["cpi"],
                     release_ids=[rels[1].id], first_seen_at=NOW, updated_at=NOW)
    st.events["dup"] = dup
    ev.release_ids.remove(rels[1].id)
    assert merge_duplicate_release_events(st) == 1
    assert "dup" not in st.events and sum(1 for e in st.events.values() if e.kind == "data_release") == 1
