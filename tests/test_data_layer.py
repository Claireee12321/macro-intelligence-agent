from datetime import date, timedelta

import pytest

from macro_intel.process.quotes import compute_change
from macro_intel.models import CalendarEvent, IndicatorSpec, MarketSpec, Observation, SeriesData
from macro_intel.process.indicators import fmt_value, transform
from macro_intel.process.releases import detect_releases, parse_forecast, surprise
from macro_intel.store import State

from .conftest import NOW


def _spec(**kw):
    base = dict(id="x", name="X", short="X", series_id="S", units="% m/m", decimals=1, frequency="M")
    base.update(kw)
    return IndicatorSpec(**base)


def _monthly(values, start=date(2025, 1, 1)):
    out = []
    for i, v in enumerate(values):
        m = start.month - 1 + i
        out.append(Observation(date=date(start.year + m // 12, m % 12 + 1, 1), value=v))
    return out


# ── transforms ───────────────────────────────────────────────────────────────

def test_pct_mom_requires_consecutive_months():
    obs = _monthly([100, 101, 102.01])
    obs.pop(1)  # gap: Jan → Mar
    assert transform(_spec(transform="pct_mom"), obs) == []
    vals = transform(_spec(transform="pct_mom"), _monthly([100, 101, 102.01]))
    assert [round(v, 2) for _, v in vals] == [1.0, 1.0]


def test_diff_yoy_and_ann3m():
    obs = _monthly([100 + i for i in range(14)])
    assert transform(_spec(transform="diff", units="K", decimals=0), obs)[-1][1] == 1
    yoy = transform(_spec(transform="pct_yoy"), obs)
    assert len(yoy) == 2 and round(yoy[-1][1], 2) == round((113 / 101 - 1) * 100, 2)
    ann = transform(_spec(transform="ann_3m"), obs)
    assert round(ann[-1][1], 3) == round(((113 / 110) ** 4 - 1) * 100, 3)


def test_fmt_value_units():
    assert fmt_value(0.3, _spec(transform="pct_mom")) == "+0.3%"
    assert fmt_value(65, _spec(transform="diff", units="K", decimals=0)) == "+65K"
    assert fmt_value(4.2, _spec(transform="level", units="%")) == "4.2%"
    assert fmt_value(-27.0, _spec(transform="level", units="$bn", decimals=0)) == "-$27bn"


# ── consensus parsing & surprise ─────────────────────────────────────────────

def test_parse_forecast_converts_units():
    assert parse_forecast("0.3%", _spec()) == 0.3
    assert parse_forecast("65K", _spec(units="K")) == 65
    assert parse_forecast("1.2M", _spec(units="K")) == 1200
    assert parse_forecast("7.15M", _spec(units="M")) == 7.15
    assert parse_forecast("65K", _spec()) is None  # unit mismatch → no consensus rather than a wrong one
    assert parse_forecast("", _spec()) is None


def test_surprise_at_published_precision():
    assert surprise(0.34, 0.3, 1) == (0.0, "in_line")
    assert surprise(0.46, 0.3, 1)[1] == "above"
    assert surprise(29.0, 65.0, 0) == (-36.0, "below")


# ── release detection ───────────────────────────────────────────────────────

def _state_with_series(values, calendar=None):
    st = State()
    st.series["S"] = SeriesData(series_id="S", observations=_monthly(values, date(2025, 9, 1)), fetched_at=NOW)
    for c in calendar or []:
        st.calendar[c.key] = c
    return st


def _cal_row(consensus=None, previous="0.2%", days_ago=0):
    d = (NOW - timedelta(days=days_ago)).date()
    return CalendarEvent(key="k1", title="CPI m/m", country="USD", region="US", date=d,
                         scheduled_at=NOW - timedelta(days=days_ago, hours=1), importance="high", family="cpi",
                         indicator_id="x", consensus=consensus, consensus_source="Forex Factory calendar (forecast)" if consensus else None,
                         previous=previous, previous_source="Forex Factory calendar", first_seen_at=NOW, updated_at=NOW)


def test_bootstrap_does_not_backfill_history():
    st = _state_with_series([100 + 0.3 * i for i in range(14)])
    spec = _spec(transform="pct_mom", release=True, family="cpi")
    assert detect_releases(st, [spec]) == []
    assert "x" in st.meta["release_watermarks"]


def test_new_period_creates_release_with_labeled_consensus():
    spec = _spec(transform="pct_mom", release=True, family="cpi", calendar_patterns=["^CPI m/m$"])
    st = _state_with_series([100 + 0.3 * i for i in range(14)])
    detect_releases(st, [spec])  # bootstrap
    st.series["S"].observations.append(Observation(date=date(2026, 11, 1), value=104.5))
    st.calendar["k1"] = _cal_row(consensus="0.2%")
    rels = detect_releases(st, [spec])
    assert len(rels) == 1
    r = rels[0]
    assert r.consensus == 0.2 and r.consensus_source.startswith("Forex Factory")
    assert r.surprise_direction == "above"
    assert r.release_time_basis == "calendar"
    assert st.calendar["k1"].actual is not None and st.calendar["k1"].status == "released"
    assert r.event_id in st.events and st.events[r.event_id].kind == "data_release"
    # Running again creates nothing new.
    assert detect_releases(st, [spec]) == []


def test_previous_is_never_used_as_consensus():
    spec = _spec(transform="pct_mom", release=True, family="cpi")
    st = _state_with_series([100 + 0.3 * i for i in range(14)])
    detect_releases(st, [spec])
    st.series["S"].observations.append(Observation(date=date(2026, 11, 1), value=104.5))
    st.calendar["k1"] = _cal_row(consensus=None, previous="0.2%")
    r = detect_releases(st, [spec])[0]
    assert r.consensus is None and r.surprise is None
    assert "No published forecast" in r.consensus_note


def test_revision_tracked_series_creates_estimate_release():
    spec = IndicatorSpec(id="gdp", name="GDP", short="GDP", series_id="G", units="% q/q saar", decimals=1,
                         frequency="Q", release=True, track_revisions=True, family="gdp")
    st = State()
    st.series["G"] = SeriesData(series_id="G", observations=[Observation(date=date(2026, 4, 1), value=2.2),
                                                             Observation(date=date(2026, 7, 1), value=3.4)], fetched_at=NOW)
    detect_releases(st, [spec])
    st.series["G"].observations[-1] = Observation(date=date(2026, 7, 1), value=3.0)
    assert detect_releases(st, [spec]) == []  # value changed but no scheduled GDP release → no event
    st.calendar["g"] = CalendarEvent(key="g", title="GDP (Second Estimate)", country="USD", region="US", date=NOW.date(),
                                     scheduled_at=NOW - timedelta(hours=1), importance="high", family="gdp",
                                     first_seen_at=NOW, updated_at=NOW)
    st.series["G"].observations[-1] = Observation(date=date(2026, 7, 1), value=3.1)
    rels = detect_releases(st, [spec])
    assert len(rels) == 1 and rels[0].id.endswith(":rev1")


# ── markets ─────────────────────────────────────────────────────────────────

def test_change_semantics():
    y = MarketSpec(id="y", label="10Y", group="t", source="treasury", units="%", change_units="bp")
    spread = MarketSpec(id="s", label="2s10s", group="c", source="derived", units="bp", change_units="bp")
    px = MarketSpec(id="p", label="SPX", group="e", source="yahoo", units="index", change_units="%")
    assert compute_change(y, 4.95, 4.90) == 5.0  # bp, not % of the yield
    assert compute_change(spread, 32.0, 34.0) == -2.0
    assert compute_change(px, 101.0, 100.0) == 1.0


@pytest.mark.parametrize("value,expected", [("4.00%", 4.0), ("7-0-2", None)])
def test_parse_forecast_rejects_non_numeric(value, expected):
    assert parse_forecast(value, _spec(units="%")) == expected


def test_calendar_visibility_policy():
    from macro_intel.publish.export import calendar_visible

    def row(country, imp, fam=None):
        return CalendarEvent(key="k", title="t", country=country, date=NOW.date(), importance=imp, family=fam,
                             first_seen_at=NOW, updated_at=NOW)
    assert calendar_visible(row("USD", "medium"))
    assert not calendar_visible(row("EUR", "medium")) and calendar_visible(row("EUR", "high"))
    assert not calendar_visible(row("AUD", "high"))  # minor G10 data hidden …
    assert calendar_visible(row("AUD", "high", "rba"))  # … but central-bank decisions shown


def test_equity_sentiment_gauge():
    from macro_intel.process.equities import sentiment

    assert sentiment(-3.8, 8.0) == "strongly negative"
    assert sentiment(-0.6, 0.5) == "negative"
    assert sentiment(0.2, -0.3) == "mixed / flat"
    assert sentiment(1.1, -2.5) == "strongly positive"
    assert sentiment(None, None) == "unavailable"


def test_fred_key_format_validation(tmp_path, monkeypatch):
    from macro_intel.config import load_settings

    monkeypatch.setenv("FRED_API_KEY", "not-a-key")
    assert load_settings(data_dir=tmp_path, load_env_file=False).fred_api_key == ""
    monkeypatch.setenv("FRED_API_KEY", '"' + "a1" * 16 + '"')
    assert load_settings(data_dir=tmp_path, load_env_file=False).fred_api_key == "a1" * 16


def test_market_headlines_are_broad_and_fresh():
    from datetime import timedelta

    from macro_intel.process.cluster import ingest_items
    from macro_intel.process.equities import headlines
    from macro_intel.store import State

    from .conftest import SRC, make_item

    st = State()
    ingest_items(st, [
        make_item("wire", "Stocks fall as the 10-year Treasury yield reclaims 5%", -1),
        make_item("wire", "There's a trade developing in energy stocks you should 'attack' now, says Jay Woods", -0.5),
        make_item("wire", "Wall Street's only Nvidia bear says forcing out CEO would be a mistake", -0.5),
        make_item("wire", "Stock futures are little changed ahead of CPI: Live updates", -19),
    ], SRC)
    titles = [h.title for h in headlines(st)]
    assert titles == ["Stocks fall as the 10-year Treasury yield reclaims 5%"]
    _ = timedelta
