"""Synthetic SAMPLE dataset — the public demo and the offline test fixture.

Everything here is fictional and labeled: headlines start with "[SAMPLE]", sources are named
"Sample …" (no real outlets), numbers are synthetic, the AI sections come from canned example text
(``SampleProvider`` — no model is called), and the exported ``meta.json`` has ``is_sample: true`` so the
website shows a prominent banner. Timestamps are relative to build time so the "Today" block is populated.
"""

from __future__ import annotations

import json
import math
import random
from datetime import date, datetime, timedelta
from pathlib import Path

from macro_intel.config import Settings
from macro_intel.collect import SourceResult
from macro_intel.models import (
    BriefingDraft,
    BriefingPoint,
    CalendarEvent,
    EventAnalysis,
    FactStatement,
    Interpretation,
    LLMUsage,
    MarketImpact,
    MarketQuote,
    MarketSnapshot,
    NewsItem,
    NewsSource,
    Observation,
    Scenario,
    SeriesData,
)
from macro_intel.process.text import canonical_url, stable_id
from macro_intel.timeutil import ET, utc_now

SAMPLE_SOURCES = [
    NewsSource(id="sample_stats", name="Sample Statistics Bureau", url="https://example.invalid/stats.xml", kind="official", tier=1, region="US", topics=["inflation"]),
    NewsSource(id="sample_cb", name="Sample Central Bank", url="https://example.invalid/cb.xml", kind="official", tier=1, region="US", topics=["monetary_policy"]),
    NewsSource(id="sample_wire", name="Sample Wire", url="https://example.invalid/wire.xml", kind="media", tier=2, region="US"),
    NewsSource(id="sample_daily", name="Sample Financial Daily", url="https://example.invalid/daily.xml", kind="media", tier=2, region="Global"),
    NewsSource(id="sample_journal", name="Sample Markets Journal", url="https://example.invalid/journal.xml", kind="media", tier=2, region="US"),
    NewsSource(id="sample_business", name="Sample Business News", url="https://example.invalid/business.xml", kind="media", tier=2, region="UK"),
]

# (source, title, hours relative to build time, summary)
_HEADLINES = [
    ("sample_stats", "Consumer Price Index rises 0.4% last month; core index up 0.3%", -3.0,
     "The all-items index rose 0.4 percent last month on a seasonally adjusted basis; the index for all items less food and energy rose 0.3 percent."),
    ("sample_wire", "US consumer prices rise more than expected as core CPI firms", -2.9,
     "Consumer prices rose more than economists expected last month, with services inflation remaining firm."),
    ("sample_daily", "Hotter CPI print revives bets on another Fed rate hike", -2.6,
     "Traders added to bets on further tightening after the inflation report beat forecasts."),
    ("sample_journal", "Treasury yields climb after inflation data; 2-year yield leads the move", -2.4,
     "Short-dated yields rose the most as investors repriced the policy outlook."),
    ("sample_journal", "Stocks fall as Treasury yields jump after hot inflation report", -1.5,
     "Major indexes slid in afternoon trading, led by rate-sensitive technology shares."),
    ("sample_wire", "Wall Street: Nasdaq leads declines as rate-hike bets build: Live updates", -0.6,
     "Stocks extended losses as investors priced a higher path for policy rates."),
    ("sample_wire", "Fed's Waller says policy may need to stay restrictive for longer", -1.0,
     "A senior Fed official said recent inflation readings argue for patience before any easing."),
    ("sample_business", "ECB holds deposit rate at 2.50%, Lagarde says inflation risks are balanced", -5.5,
     "The euro-area central bank kept rates unchanged and signalled a data-dependent path."),
    ("sample_daily", "Euro area inflation edges up to 2.4% in flash estimate", -26.0,
     "Euro-area consumer price inflation rose slightly in the latest flash estimate."),
    ("sample_wire", "Oil falls as producers signal output increase next quarter", -8.0,
     "Crude prices fell after major producers indicated higher supply."),
    ("sample_journal", "Bitcoin hits new record as crypto ETFs see inflows", -6.0,
     "Not macro: included to show that off-topic items are filtered out."),
]


def _items(now: datetime) -> list[NewsItem]:
    by_id = {s.id: s for s in SAMPLE_SOURCES}
    out = []
    for n, (sid, title, hours, summary) in enumerate(_HEADLINES):
        src = by_id[sid]
        url = f"https://example.invalid/{sid}/{n}"
        out.append(NewsItem(
            id=stable_id(canonical_url(url)), source_id=sid, source_name=src.name, source_kind=src.kind,
            source_tier=src.tier, url=url, title=f"[SAMPLE] {title}", summary=f"Sample text: {summary}",
            published_at=now + timedelta(hours=hours), collected_at=now, region=src.region,
        ))
    return out


# ── Synthetic series (plausible shapes, fictional values) ───────────────────

def _month(d0: date, i: int) -> date:
    m = d0.month - 1 + i
    return date(d0.year + m // 12, m % 12 + 1, 1)


def _index(start: date, n: int, base: float, monthly_pct: float, wiggle: float, tail: tuple[float, ...] = ()) -> list[Observation]:
    """Index level series; ``tail`` fixes the last monthly % steps exactly (e.g. a hot latest print)."""
    v, out = base, []
    for i in range(n):
        k = i - (n - len(tail))
        step = tail[k] if k >= 0 else monthly_pct + wiggle * math.sin(i / 2.3)
        v *= 1 + step / 100
        out.append(Observation(date=_month(start, i), value=round(v, 4)))
    return out


def _level(start: date, n: int, base: float, amp: float, period: float = 9.0, drift: float = 0.0, decimals: int = 2) -> list[Observation]:
    return [Observation(date=_month(start, i), value=round(base + drift * i + amp * math.sin(i / period * 2 * math.pi), decimals))
            for i in range(n)]


def _daily(end: date, days: int, base: float, drift: float, amp: float, decimals: int = 4) -> list[Observation]:
    out = []
    for i in range(days):
        d = end - timedelta(days=days - 1 - i)
        if d.weekday() < 5:
            out.append(Observation(date=d, value=round(base + drift * (i - days) + amp * math.sin(i / 11.0), decimals)))
    return out


def sample_series(settings: Settings, now: datetime) -> dict[str, SeriesData]:
    today = now.astimezone(ET).date()
    last = _month(date(today.year, today.month, 1), -1)  # latest monthly observation = last month
    n = 8 * 12 + 1
    start = _month(last, -(n - 1))
    qn = 32
    q_last = date(last.year, ((last.month - 1) // 3) * 3 + 1, 1)
    custom: dict[str, list[Observation]] = {
        "CPIAUCSL": _index(start, n, 250.0, 0.22, 0.05, tail=(0.33, 0.30, 0.40)),
        "CPIAUCNS": _index(start, n, 250.4, 0.22, 0.05, tail=(0.33, 0.30, 0.40)),
        "CPILFESL": _index(start, n, 260.0, 0.23, 0.03, tail=(0.31, 0.33, 0.30)),
        "CPILFENS": _index(start, n, 260.2, 0.23, 0.03, tail=(0.31, 0.33, 0.30)),
        "PCEPI": _index(start, n, 110.0, 0.22, 0.05),
        "PCEPILFE": _index(start, n, 112.0, 0.23, 0.03, tail=(0.29, 0.31, 0.30)),
        "PPIFIS": _index(start, n, 130.0, 0.24, 0.20, tail=(0.35, 0.40, 0.38)),
        "PPIFES": _index(start, n, 131.0, 0.22, 0.08),
        "PAYEMS": _index(start, n, 151000.0, 0.10, 0.03),
        "CES0500000003": _index(start, n, 29.0, 0.32, 0.05),
        "RSAFS": _index(start, n, 620000.0, 0.35, 0.40),
        "RSFSXMV": _index(start, n, 500000.0, 0.33, 0.30),
        "INDPRO": _index(start, n, 101.0, 0.05, 0.30),
        "PCEC96": _index(start, n, 15000.0, 0.20, 0.12),
        "UNRATE": _level(start, n, 4.1, 0.15, decimals=1),
        "JTSJOL": _level(start, n, 7400.0, 300.0, decimals=0),
        "UMCSENT": _level(start, n, 62.0, 6.0, decimals=1),
        "MICH": _level(start, n - 4, 3.2, 0.2, decimals=1) + [
            Observation(date=_month(start, n - 4 + i), value=v) for i, v in enumerate((3.2, 3.3, 3.5, 3.7))],
        "HOUST": _level(start, n, 1350.0, 60.0, decimals=0),
        "MTSDS133FMS": _level(start, n, -150000.0, 90000.0, period=4.0, decimals=0),
        "CP0000EZ19M086NEST": _index(start, n, 115.0, 0.18, 0.05),
        "A191RL1Q225SBEA": [Observation(date=_month(q_last, -3 * (qn - 1 - i)), value=round(2.1 + 0.9 * math.sin(i / 2.0), 1)) for i in range(qn)],
        "GFDEBTN": [Observation(date=_month(q_last, -3 * (qn - 1 - i)), value=round(30_000_000 + 280_000 * i, 0)) for i in range(qn)],
    }
    yesterday = today - timedelta(days=1)
    daily = {
        "DFEDTARU": (4.00, 0.0, 0.0, 2), "DFEDTARL": (3.75, 0.0, 0.0, 2), "EFFR": (3.88, 0.0, 0.0, 2),
        "DGS2": (4.50, 0.0004, 0.08, 2), "DFII10": (2.60, 0.0002, 0.06, 2), "T5YIE": (2.30, 0.0, 0.05, 2),
        "T10YIE": (2.28, 0.0, 0.04, 2), "T5YIFR": (2.25, 0.0, 0.03, 2), "BAMLH0A0HYM2": (3.20, -0.0005, 0.15, 2),
        "BAMLC0A0CM": (0.90, -0.0001, 0.04, 2), "VIXCLS": (17.0, 0.0, 2.5, 2), "DTWEXBGS": (121.0, 0.002, 0.8, 2),
        "RRPONTSYD": (5.0, 0.0, 3.0, 0), "THREEFYTP10": (0.85, 0.0, 0.06, 2),
    }
    weekly = {"ICSA": (215000.0, 9000.0, 0), "CCSA": (1850000.0, 30000.0, 0), "NFCI": (-0.45, 0.05, 3),
              "STLFSI4": (-0.50, 0.08, 3), "WALCL": (6_700_000.0, 20_000.0, 0), "WRESBAL": (2_900_000.0, 60_000.0, 0)}
    series: dict[str, SeriesData] = {}
    sids = {s.series_id for s in settings.indicators} | {m.symbol for m in settings.markets if m.source == "fred"}
    for sid in sorted(sids):
        if sid in custom:
            obs = custom[sid]
        elif sid in daily:
            base, drift, amp, dec = daily[sid]
            obs = _daily(yesterday, 420, base, drift, amp, dec)
            if sid == "DFEDTARU":  # a 25bp hike ~70 days ago
                obs = [Observation(date=o.date, value=3.75 if (yesterday - o.date).days > 70 else 4.00) for o in obs]
            if sid == "DFEDTARL":
                obs = [Observation(date=o.date, value=3.50 if (yesterday - o.date).days > 70 else 3.75) for o in obs]
        elif sid in weekly:
            base, amp, dec = weekly[sid]
            last_sat = yesterday - timedelta(days=(yesterday.weekday() - 5) % 7 + 7)
            obs = [Observation(date=last_sat - timedelta(days=7 * (150 - i)), value=round(base + amp * math.sin(i / 5.0), dec)) for i in range(151)]
        else:
            obs = _daily(yesterday, 420, 4.0, 0.0, 0.1, 2)
        series[sid] = SeriesData(series_id=sid, source="sample", observations=obs, fetched_at=now, vintage="SAMPLE (synthetic)")
    return series


# ── Synthetic market snapshot ────────────────────────────────────────────────

_LEVELS = {
    "ust_3m": 4.21, "ust_2y": 4.62, "ust_5y": 4.70, "ust_10y": 4.93, "ust_30y": 5.20, "live_2y_fut": 102.10,
    "live_5y": 4.71, "live_10y": 4.94, "live_30y": 5.21, "tips_5y": 2.40, "tips_10y": 2.66, "fwd_5y5y": 2.26,
    "fed_upper": 4.00, "effr": 3.88, "sofr": 3.95, "dxy": 101.8, "eurusd": 1.1180, "usdjpy": 158.4, "gbpusd": 1.3420,
    "usdcnh": 7.0950, "audusd": 0.6980, "usdcad": 1.3950, "ecb_eurusd": 1.1172, "ecb_usdjpy": 158.1, "ecb_gbpusd": 1.3410,
    "hy_oas": 3.30, "ig_oas": 0.92, "nfci": -0.45, "vix": 19.8, "wti": 84.2, "brent": 88.9, "gold": 4020.0, "copper": 6.10,
    "natgas": 3.10, "spx": 7420.0, "dji": 51800.0, "ixic": 24600.0, "rut": 2790.0, "spx_ew": 214.5,
}
_FLAT = {"fed_upper", "effr", "sofr", "ecb_eurusd", "ecb_usdjpy", "ecb_gbpusd"}
_TODAY_MOVE = {  # today's change: yields up (bp/100), stocks down — a "hot CPI" day
    "ust_2y": 0.09, "ust_5y": 0.08, "ust_10y": 0.06, "ust_30y": 0.04, "ust_3m": 0.01, "live_5y": 0.08, "live_10y": 0.06,
    "live_30y": 0.04, "tips_5y": 0.05, "tips_10y": 0.04, "live_2y_fut": -0.12, "dxy": 0.55, "eurusd": -0.006,
    "usdjpy": 0.9, "gbpusd": -0.005, "spx": -85.0, "dji": -360.0, "ixic": -390.0, "rut": -38.0, "spx_ew": -1.6,
    "vix": 2.6, "gold": -30.0, "wti": -0.9, "hy_oas": 0.06, "ig_oas": 0.01,
}


def sample_snapshot(settings: Settings, now: datetime) -> MarketSnapshot:
    from macro_intel.process.quotes import compute_change

    today = now.astimezone(ET).date()
    quotes = {}
    for i, m in enumerate(settings.markets):
        level = _LEVELS.get(m.id)
        if level is None:
            continue
        rng = random.Random(m.id)  # deterministic per instrument
        vol = 0.0 if m.id in _FLAT else 0.0045
        days = [today - timedelta(days=90 - j) for j in range(90) if (today - timedelta(days=90 - j)).weekday() < 5]
        walk, v = [], level
        for _ in days:  # random walk that ends near the target level
            v *= 1 + rng.gauss(0, vol)
            walk.append(v)
        shift = level - walk[-1]
        hist = [(d.isoformat(), round(w + shift * (k + 1) / len(walk), 4)) for k, (d, w) in enumerate(zip(days, walk))]
        last_prev = hist[-1][1]
        hist.append((today.isoformat(), round(last_prev + _TODAY_MOVE.get(m.id, 0.0), 4)))
        scale = m.scale
        hist = [(dd, v * scale) for dd, v in hist]
        q = MarketQuote(id=m.id, label=m.label, group=m.group, units=m.units, decimals=m.decimals,
                        change_units=m.change_units, value=hist[-1][1], prev_value=hist[-2][1], prev_label=hist[-2][0],
                        as_of=now - timedelta(minutes=20), as_of_label="SAMPLE — synthetic", kind="intraday",
                        source="SAMPLE (synthetic)", history=hist, note=m.note)
        q.change = compute_change(m, q.value, q.prev_value)
        quotes[m.id] = q
    for m in settings.markets:  # derived spreads from the synthetic legs
        if m.source == "derived" and m.formula:
            a, b = [x.strip() for x in m.formula.split("-")]
            if a in quotes and b in quotes:
                ha, hb = dict(quotes[a].history), dict(quotes[b].history)
                mult = 100.0 if m.units == "bp" else 1.0
                hist = [(dd, (ha[dd] - hb[dd]) * mult) for dd in sorted(set(ha) & set(hb))]
                q = MarketQuote(id=m.id, label=m.label, group=m.group, units=m.units, decimals=m.decimals,
                                change_units=m.change_units, value=hist[-1][1], prev_value=hist[-2][1],
                                as_of=now - timedelta(minutes=20), as_of_label="SAMPLE — synthetic", kind="derived",
                                source="SAMPLE (synthetic)", history=hist)
                q.change = compute_change(m, q.value, q.prev_value)
                quotes[m.id] = q
    return MarketSnapshot(taken_at=now, quotes=quotes, source_status={"sample": "ok"})


# ── Synthetic calendar ───────────────────────────────────────────────────────

def sample_calendar(now: datetime, state) -> int:
    t = now
    rows = [
        # title, indicator, family, importance, when, consensus, previous, country
        ("CPI m/m", "us_cpi_mom", "cpi", "high", t - timedelta(hours=3), "0.3%", "0.3%", "USD"),
        ("Core CPI m/m", "us_core_cpi_mom", "cpi", "high", t - timedelta(hours=3), "0.2%", "0.3%", "USD"),
        ("Main Refinancing Rate", None, "ecb", "high", t - timedelta(hours=5, minutes=45), "2.65%", "2.65%", "EUR"),
        ("Monetary Policy Statement", None, "ecb", "high", t - timedelta(hours=5, minutes=45), None, None, "EUR"),
        ("Unemployment Claims", "us_claims", "jobless_claims", "medium", t + timedelta(days=1), "218K", "215K", "USD"),
        ("Non-Farm Employment Change", "us_payrolls", "us_payrolls", "high", t + timedelta(days=2), "120K", "95K", "USD"),
        ("Unemployment Rate", "us_unrate", "us_payrolls", "high", t + timedelta(days=2), "4.2%", "4.2%", "USD"),
        ("Retail Sales m/m", "us_retail_mom", "retail_sales", "medium", t + timedelta(days=3), None, "0.4%", "USD"),
        ("Federal Funds Rate", "us_fed_upper", "fed", "high", t + timedelta(days=6), "4.00%", "4.00%", "USD"),
    ]
    for title, ind, fam, imp, when, cons, prev, ctry in rows:
        d = when.astimezone(ET).date()
        key = stable_id("sample", title, d.isoformat())
        state.calendar[key] = CalendarEvent(
            key=key, title=f"[SAMPLE] {title}", country=ctry, region={"USD": "US", "EUR": "EA"}[ctry], date=d,
            scheduled_at=when, importance=imp, family=fam, indicator_id=ind, consensus=cons,
            consensus_source="SAMPLE calendar (forecast)" if cons else None, previous=prev,
            previous_source="SAMPLE calendar" if prev else None, sources=["sample"], first_seen_at=now, updated_at=now,
        )
    return len(rows)


# ── Canned AI output (no model is called) ───────────────────────────────────

_CPI_ANALYSIS = EventAnalysis(
    headline="[SAMPLE] CPI rose 0.4% m/m (core 0.3%), above published forecasts",
    summary=("Sample AI analysis: inflation came in a tenth above forecasts on both headline and core, extending a run "
             "of firm services prices. That strengthens the case for policy staying restrictive and pushes back on "
             "expectations of near-term easing."),
    facts=[FactStatement(text="Headline CPI rose 0.4% m/m and core CPI 0.3% m/m in the latest month.", refs=["R1", "I1"]),
           FactStatement(text="Both readings were 0.1pp above the published forecasts.", refs=["R1", "R2"]),
           FactStatement(text="Outlets reported higher bets on further tightening after the release.", refs=["I3"])],
    expectations="Published forecasts were +0.3% m/m headline and +0.2% m/m core; both prints beat by 0.1pp.",
    economic_interpretation=[
        Interpretation(dimension="inflation", assessment="Underlying inflation momentum is not cooling.",
                       reasoning="A 0.3% core print annualises to well above a 2% target; three-month momentum rises."),
        Interpretation(dimension="monetary_policy", assessment="Raises the bar for any rate cut; keeps a hike on the table.",
                       reasoning="Policymakers have tied the path to inflation progress, which this print does not show."),
        Interpretation(dimension="growth", assessment="Little direct signal for activity.",
                       reasoning="Higher prices squeeze real incomes at the margin, but labor demand remains solid."),
    ],
    narrative_effect="reinforces",
    narrative_explanation="Consistent with the rule-based regime (inflation: accelerating; policy: tightening).",
    market_impacts=[
        MarketImpact(asset="front_end_rates", instrument="2Y Treasury yield", direction="up", strength="strong", confidence="high",
                     horizon="days", mechanism="Higher expected policy path is priced first at the front end."),
        MarketImpact(asset="yield_curve", instrument="2s10s", direction="flatter", strength="moderate", confidence="medium",
                     horizon="days", mechanism="Front end reprices more than the long end when policy expectations rise."),
        MarketImpact(asset="usd", instrument="DXY", direction="stronger", strength="moderate", confidence="medium",
                     horizon="days", mechanism="Wider rate differentials versus other major economies."),
        MarketImpact(asset="equities", instrument="S&P 500", direction="down", strength="moderate", confidence="low",
                     horizon="intraday", mechanism="Higher discount rates weigh on long-duration (growth) equities."),
    ],
    alternative_scenarios=[
        Scenario(scenario="One-off from volatile components", implications="If next month's core cools to 0.2%, the repricing could partly reverse."),
        Scenario(scenario="Broadening services inflation", implications="A further hike would move from possible to likely; curve flattens further."),
    ],
    reaction_consistency="consistent",
    reaction_explanation="The observed moves (2Y yield up most, dollar up, stocks down) match the expected direction.",
    watch_next=["Next week's payrolls and wage growth", "PCE price index", "Fed speakers' reaction"],
    invalidation_triggers=["A sharp drop in core goods or services prices next month", "A clear weakening in the labor market"],
    key_uncertainties=["How much of the beat is seasonal noise", "Pass-through from energy prices"],
)

_ECB_ANALYSIS = EventAnalysis(
    headline="[SAMPLE] ECB holds rates; guidance stays data-dependent",
    summary="Sample AI analysis: an expected hold with balanced guidance; limited spillover to US markets beyond EUR/USD.",
    facts=[FactStatement(text="The ECB kept its deposit rate unchanged.", refs=["I1"])],
    expectations="The published forecast expected no change.",
    economic_interpretation=[Interpretation(dimension="global_spillovers", assessment="Small.",
                                            reasoning="No surprise relative to the published forecast.")],
    narrative_effect="unclear", narrative_explanation="Little new information for the US regime.",
    market_impacts=[MarketImpact(asset="fx_other", instrument="EUR/USD", direction="mixed", strength="weak", confidence="low",
                                 horizon="days", mechanism="No policy surprise; driven by US data today.")],
    alternative_scenarios=[], reaction_consistency="insufficient_data",
    reaction_explanation="Moves today are dominated by US inflation data.",
    watch_next=["Euro area inflation flash estimate"], invalidation_triggers=[], key_uncertainties=[],
)


_FED_SPEECH_ANALYSIS = EventAnalysis(
    headline="[SAMPLE] Fed official signals rates may stay restrictive for longer",
    summary="Sample AI analysis: a senior official's remarks echo the inflation data and lean against early easing.",
    facts=[FactStatement(text="A Fed official said policy may need to stay restrictive for longer.", refs=["I1"])],
    expectations="Speeches have no published consensus; the remarks are judged against prior guidance.",
    economic_interpretation=[Interpretation(dimension="monetary_policy", assessment="Hawkish tilt.",
                                            reasoning="Ties the path explicitly to inflation progress, which today's data did not show.")],
    narrative_effect="reinforces", narrative_explanation="Adds to the 'policy tightening' read.",
    market_impacts=[MarketImpact(asset="policy_expectations", instrument="Fed funds path", direction="up", strength="weak",
                                 confidence="medium", horizon="weeks", mechanism="Signals a higher-for-longer path.")],
    alternative_scenarios=[Scenario(scenario="Isolated view", implications="If other officials push back, the impact fades.")],
    reaction_consistency="insufficient_data", reaction_explanation="Speeches have no precise timestamp to measure from.",
    watch_next=["Other Fed speakers this week"], invalidation_triggers=["A dovish shift from the Chair"], key_uncertainties=[],
)


class SampleProvider:
    """Returns canned, clearly labeled example analyses — demonstrates the AI sections without a model."""

    name = "sample"
    model = "sample-fixture (no model call)"

    def generate(self, system, user, schema, max_tokens=16000):
        packet = json.loads(user)
        if schema is EventAnalysis:
            title = (packet.get("event") or {}).get("title", "")
            if "ECB" in title:
                pick = _ECB_ANALYSIS
            elif "CPI" in title:
                pick = _CPI_ANALYSIS
            elif "Fed" in title:
                pick = _FED_SPEECH_ANALYSIS
            else:
                pick = _ECB_ANALYSIS.model_copy(update={
                    "headline": f"{title}", "summary": "Sample AI analysis: limited direct spillover to US markets today.",
                    "facts": [FactStatement(text="See the cited source for details.", refs=["I1"])]})
            return pick.model_copy(deep=True), LLMUsage()
        ids = {e["title"]: e["event_id"] for e in packet.get("events", [])}

        def eid(word: str) -> list[str]:
            return [v for k, v in ids.items() if word.lower() in k.lower()][:1]

        return BriefingDraft(
            headline="[SAMPLE] Hot CPI lifts yields and the dollar; stocks slide",
            overview=("Sample AI briefing: Consumer inflation beat forecasts on headline and core, reinforcing the "
                      "'inflation accelerating, policy tightening' regime. Front-end Treasury yields led a broad repricing "
                      "of the policy path, the dollar firmed and equities fell. The ECB's hold had little cross-asset impact."),
            us_equity_market=("Sample: US stocks fell in afternoon trade as yields jumped after the inflation report; the "
                              "Nasdaq lagged and the VIX rose, a risk-off tone driven by rates rather than growth fears."),
            key_developments=[BriefingPoint(text="CPI beat forecasts by 0.1pp on headline and core.", event_ids=eid("CPI")),
                              BriefingPoint(text="ECB held rates as expected.", event_ids=eid("ECB"))],
            what_changed="The market moved further toward pricing another hike; the regime read is reinforced, not changed.",
            market_implications=[BriefingPoint(text="Front-end yields up most → curve flatter; dollar stronger.", event_ids=eid("CPI")),
                                 BriefingPoint(text="Equities pressured via discount rates; credit spreads little changed.")],
            what_to_watch=[BriefingPoint(text="Payrolls and wages in two days — a strong print would cement hike pricing.")],
            risks=["Inflation beat proves seasonal noise", "Growth slowdown shifts focus from inflation"],
        ), LLMUsage()


# ── Wiring ───────────────────────────────────────────────────────────────────

class SampleCollectors:
    """Synthetic implementation of ``macro_intel.collect.Collectors`` — the reference example for writing
    your own collectors, and the source of the public demo. Makes no network requests."""

    name = "sample"

    def __init__(self, settings: Settings, now: datetime | None = None):
        self.now = now or utc_now()
        self._items = _items(self.now)
        self._series = sample_series(settings, self.now)
        self._snap = sample_snapshot(settings, self.now)

    def fetch_news(self, sources, timeout):
        return [i.model_copy(deep=True) for i in self._items], [SourceResult(s.id, ok=True, fetched=1, kept=1) for s in SAMPLE_SOURCES]

    def update_series(self, series, requests, api_key):
        for sid, data in self._series.items():
            series[sid] = data.model_copy(deep=True)
        return {}

    def update_calendar(self, state, settings):
        return {"sample_calendar": sample_calendar(self.now, state)}

    def market_snapshot(self, specs, series):
        return self._snap.model_copy(deep=True)


def write_sample(settings: Settings) -> Path:
    """One offline cycle on sample data into ``<root>/data-sample`` (or --data-dir), labeled as SAMPLE."""
    import shutil

    from macro_intel.pipeline import run_cycle
    from macro_intel.publish.export import build_bundle, write_bundle
    from macro_intel.store import Store

    if settings.data_dir.name == "data":
        settings.data_dir = settings.root / "data-sample"
    if settings.data_dir.exists():
        meta = settings.data_dir / "site" / "meta.json"
        is_sample_dir = "sample" in settings.data_dir.name or (
            meta.exists() and json.loads(meta.read_text(encoding="utf-8")).get("is_sample") is True)
        if not is_sample_dir:
            raise SystemExit(f"Refusing to overwrite {settings.data_dir}: it does not look like a sample dataset.")
        shutil.rmtree(settings.data_dir)  # always a fresh, deterministic sample day
    settings.sources = list(SAMPLE_SOURCES)
    settings.llm_provider = "none"
    settings.llm_min_importance = 55
    # Never attribute synthetic numbers to real agencies.
    settings.indicators = [s.model_copy(update={"source_name": "SAMPLE (synthetic)"}) for s in settings.indicators]
    run_cycle(settings, trigger="sample", provider_override=SampleProvider(), collectors=SampleCollectors(settings))
    state = Store(settings.state_dir).load()
    write_bundle(build_bundle(state, settings, is_sample=True), settings.site_dir)
    return settings.site_dir
