"""Deterministic macro-regime assessment (MVP methodology; see docs/ARCHITECTURE.md §Regime).

Each dimension aggregates simple, documented threshold rules into a weighted score in [-1, 1]:
  growth:               +1 accelerating … -1 slowing      (±0.33 cut-offs)
  inflation:            +1 accelerating … -1 cooling      (±0.33)
  financial conditions: +1 tightening   … -1 easing       (±0.33)
  monetary policy:      rule-based state (recent rate changes, real policy rate)
Every evidence row carries its value, observation period and the rule applied. The LLM may
*explain* this evidence but never sets the classification.
"""

from __future__ import annotations

from datetime import date, timedelta

from macro_intel.models import IndicatorSpec, MacroState, RegimeDimension, RegimeEvidence, SeriesData
from macro_intel.process.indicators import period_label, transform
from macro_intel.timeutil import utc_now

Series = list[tuple[date, float]]


class _Data:
    def __init__(self, specs: list[IndicatorSpec], series: dict[str, SeriesData]):
        self.specs = {s.id: s for s in specs}
        self.series = series

    def get(self, indicator_id: str) -> Series:
        spec = self.specs.get(indicator_id)
        if not spec or spec.series_id not in self.series:
            return []
        return transform(spec, self.series[spec.series_id].observations)

    def raw(self, series_id: str) -> Series:
        sd = self.series.get(series_id)
        return [(o.date, o.value) for o in sd.observations] if sd else []

    def freq(self, indicator_id: str) -> str:
        spec = self.specs.get(indicator_id)
        return spec.frequency if spec else "D"


def _avg(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def _value_ago(s: Series, days: int) -> tuple[date, float] | None:
    if not s:
        return None
    target = s[-1][0] - timedelta(days=days)
    prior = [(d, v) for d, v in s if d <= target]
    return prior[-1] if prior else None


def _signal(x: float, up: float, down: float) -> int:
    return 1 if x > up else -1 if x < down else 0


def _classify(score: float | None, pos: str, neutral: str, neg: str) -> str:
    if score is None:
        return "insufficient data"
    return pos if score > 0.33 else neg if score < -0.33 else neutral


def _finish(dim: str, ev: list[RegimeEvidence], gaps: list[str], labels: tuple[str, str, str], min_n: int, method: str) -> RegimeDimension:
    tot_w = sum(e.weight for e in ev)
    score = round(sum(e.signal * e.weight for e in ev) / tot_w, 2) if ev and len(ev) >= min_n else None
    return RegimeDimension(
        dimension=dim, state=_classify(score, *labels), score=score, evidence=ev, data_gaps=gaps,
        as_of=max((e.as_of for e in ev), default=None), method=method,
    )


def growth(d: _Data) -> RegimeDimension:
    ev, gaps = [], []
    p = d.get("us_payrolls")
    if len(p) >= 12:
        a3, a12 = _avg([v for _, v in p[-3:]]), _avg([v for _, v in p[-12:]])
        ev.append(RegimeEvidence(indicator="Payrolls", display=f"3m avg {a3:+.0f}K vs 12m avg {a12:+.0f}K",
                                 as_of=period_label(p[-1][0], "M"), signal=_signal(a3 - a12, 25, -25),
                                 rule="3m avg minus 12m avg: > +25K accelerating, < -25K slowing"))
    else:
        gaps.append("payrolls")
    u = d.get("us_unrate")
    if len(u) >= 15:
        a3 = _avg([v for _, v in u[-3:]])
        low12 = min(v for _, v in u[-15:-3])
        diff = a3 - low12
        ev.append(RegimeEvidence(indicator="Unemployment rate", display=f"3m avg {a3:.2f}% vs prior-12m low {low12:.1f}% ({diff:+.2f}pp)",
                                 as_of=period_label(u[-1][0], "M"), signal=-1 if diff >= 0.3 else (1 if diff <= 0.0 else 0),
                                 rule="Sahm-style: rise ≥ 0.30pp slowing; at/below prior low accelerating"))
    else:
        gaps.append("unemployment rate")
    g = d.get("us_gdp")
    if len(g) >= 5:
        prior = _avg([v for _, v in g[-5:-1]])
        ev.append(RegimeEvidence(indicator="Real GDP", display=f"{g[-1][1]:.1f}% saar vs prior-4Q avg {prior:.1f}%",
                                 as_of=period_label(g[-1][0], "Q"), signal=_signal(g[-1][1] - prior, 0.75, -0.75),
                                 rule="latest minus prior-4Q average: > +0.75pp accelerating, < -0.75pp slowing"))
    else:
        gaps.append("real GDP")
    ip = d.raw("INDPRO")
    if len(ip) >= 7:
        ann = ((_avg([v for _, v in ip[-3:]]) / _avg([v for _, v in ip[-6:-3]])) ** 4 - 1) * 100
        ev.append(RegimeEvidence(indicator="Industrial production", display=f"3m/3m annualized {ann:+.1f}%",
                                 as_of=period_label(ip[-1][0], "M"), signal=_signal(ann, 2.0, -2.0), weight=0.5,
                                 rule="3m/3m annualized: > +2% accelerating, < -2% slowing"))
    else:
        gaps.append("industrial production")
    rp = d.raw("PCEC96")
    if len(rp) >= 7:
        ann = ((_avg([v for _, v in rp[-3:]]) / _avg([v for _, v in rp[-6:-3]])) ** 4 - 1) * 100
        ev.append(RegimeEvidence(indicator="Real consumer spending", display=f"3m/3m annualized {ann:+.1f}%",
                                 as_of=period_label(rp[-1][0], "M"), signal=_signal(ann, 3.0, 1.0),
                                 rule="3m/3m annualized: > +3% accelerating, < +1% slowing"))
    else:
        gaps.append("real consumer spending")
    c = d.get("us_claims")
    if len(c) >= 26:
        a4, a26 = _avg([v for _, v in c[-4:]]), _avg([v for _, v in c[-26:]])
        pct = (a4 / a26 - 1) * 100
        ev.append(RegimeEvidence(indicator="Initial claims", display=f"4wk avg {a4:.0f}K vs 26wk avg {a26:.0f}K ({pct:+.1f}%)",
                                 as_of=period_label(c[-1][0], "W"), signal=-1 if pct > 10 else (1 if pct < -5 else 0), weight=0.5,
                                 rule="4wk vs 26wk avg: > +10% slowing, < -5% accelerating"))
    else:
        gaps.append("initial claims")
    return _finish("growth", ev, gaps, ("accelerating", "stable", "slowing"), 3,
                   "Weighted vote of labor, output and spending momentum rules (US).")


def inflation(d: _Data) -> RegimeDimension:
    ev, gaps = [], []
    for ind3, ind12, label, w in (("us_core_cpi_3m", "us_core_cpi_yoy", "Core CPI", 1.0),):
        s3, s12 = d.get(ind3), d.get(ind12)
        if s3 and s12:
            diff = s3[-1][1] - s12[-1][1]
            ev.append(RegimeEvidence(indicator=label, display=f"3m annualized {s3[-1][1]:.1f}% vs y/y {s12[-1][1]:.1f}%",
                                     as_of=period_label(s3[-1][0], "M"), signal=_signal(diff, 0.4, -0.4), weight=w,
                                     rule="3m annualized minus y/y: > +0.4pp accelerating, < -0.4pp cooling"))
        else:
            gaps.append(label)

    def _ann3_vs_yoy(series_id: str, label: str, weight: float):
        raw = d.raw(series_id)
        if len(raw) >= 13:
            ann = ((raw[-1][1] / raw[-4][1]) ** 4 - 1) * 100
            yoy = (raw[-1][1] / raw[-13][1] - 1) * 100
            ev.append(RegimeEvidence(indicator=label, display=f"3m annualized {ann:.1f}% vs y/y {yoy:.1f}%",
                                     as_of=period_label(raw[-1][0], "M"), signal=_signal(ann - yoy, 0.4, -0.4), weight=weight,
                                     rule="3m annualized minus y/y: > +0.4pp accelerating, < -0.4pp cooling"))
        else:
            gaps.append(label)

    _ann3_vs_yoy("PCEPILFE", "Core PCE", 1.0)
    _ann3_vs_yoy("CPIAUCSL", "Headline CPI", 0.5)
    _ann3_vs_yoy("PPIFIS", "PPI final demand", 0.5)
    be = d.raw("T5YIE")
    ago = _value_ago(be, 30)
    if be and ago:
        chg = (be[-1][1] - ago[1]) * 100
        ev.append(RegimeEvidence(indicator="5y breakeven", display=f"{be[-1][1]:.2f}% ({chg:+.0f}bp over 1m)",
                                 as_of=be[-1][0].isoformat(), signal=_signal(chg, 15, -15), weight=0.5,
                                 rule="1-month change: > +15bp accelerating, < -15bp cooling"))
    else:
        gaps.append("5y breakeven")
    m = d.get("us_mich_1y")
    if len(m) >= 4:
        chg = m[-1][1] - m[-4][1]
        ev.append(RegimeEvidence(indicator="UMich 1y expectations", display=f"{m[-1][1]:.1f}% ({chg:+.1f}pp vs 3m earlier)",
                                 as_of=period_label(m[-1][0], "M"), signal=_signal(chg, 0.3, -0.3), weight=0.5,
                                 rule="3-month change: > +0.3pp accelerating, < -0.3pp cooling"))
    else:
        gaps.append("UMich 1y expectations")
    return _finish("inflation", ev, gaps, ("accelerating", "stable", "cooling"), 3,
                   "Short-run (3m annualized) vs 12m inflation momentum, plus market/survey expectations (US).")


def monetary_policy(d: _Data) -> RegimeDimension:
    ev, gaps = [], []
    up = d.raw("DFEDTARU")
    state = "insufficient data"
    if up:
        last_change = None
        for (d0, v0), (d1, v1) in zip(up, up[1:]):
            if abs(v1 - v0) > 1e-9:
                last_change = (d1, v1 - v0)
        cur = up[-1][1]
        if last_change:
            days = (up[-1][0] - last_change[0]).days
            ev.append(RegimeEvidence(indicator="Fed funds target (upper)", display=f"{cur:.2f}%; last change {last_change[1] * 100:+.0f}bp on {last_change[0].isoformat()} ({days} days ago)",
                                     as_of=up[-1][0].isoformat(), signal=1 if last_change[1] > 0 else -1,
                                     rule="a change within the last 120 days sets the direction (tightening / easing)"))
            if days <= 120:
                state = "tightening" if last_change[1] > 0 else "easing"
        else:
            ev.append(RegimeEvidence(indicator="Fed funds target (upper)", display=f"{cur:.2f}%; no change in the data window",
                                     as_of=up[-1][0].isoformat(), signal=0, rule="no recent change"))
    else:
        gaps.append("fed funds target")
    effr = d.raw("EFFR")
    core = d.get("us_core_pce_yoy")
    if effr and core:
        real = effr[-1][1] - core[-1][1]
        ev.append(RegimeEvidence(indicator="Real policy rate", display=f"EFFR {effr[-1][1]:.2f}% minus core PCE y/y {core[-1][1]:.1f}% = {real:+.2f}pp",
                                 as_of=effr[-1][0].isoformat(), signal=1 if real > 1.0 else (-1 if real < 0 else 0),
                                 rule="> +1.0pp restrictive, < 0 accommodative, otherwise neutral"))
        if state == "insufficient data" or state not in ("tightening", "easing"):
            state = "restrictive" if real > 1.0 else ("accommodative" if real < 0 else "neutral")
    else:
        gaps.append("real policy rate")
    two = d.raw("DGS2")
    if two and effr:
        spread = (two[-1][1] - effr[-1][1]) * 100
        ev.append(RegimeEvidence(indicator="2Y Treasury minus EFFR", display=f"{spread:+.0f}bp",
                                 as_of=two[-1][0].isoformat(), signal=1 if spread > 25 else (-1 if spread < -25 else 0), weight=0,
                                 rule="market-implied path (context only): > +25bp hikes priced, < -25bp cuts priced"))
    return RegimeDimension(dimension="monetary_policy", state=state, evidence=ev, data_gaps=gaps,
                           as_of=max((e.as_of for e in ev), default=None),
                           method="Recent target-range changes set direction; otherwise the real policy rate sets the stance. 2Y–EFFR shown as context.")


def financial_conditions(d: _Data) -> RegimeDimension:
    ev, gaps = [], []

    def _chg_rule(series_id, label, days, mult, up, down, unit, weight=1.0, fmt="{:.2f}"):
        s = d.raw(series_id)
        ago = _value_ago(s, days)
        if s and ago:
            chg = (s[-1][1] - ago[1]) * mult
            ev.append(RegimeEvidence(indicator=label, display=f"{fmt.format(s[-1][1])} ({chg:+.1f}{unit} over {days}d)",
                                     as_of=s[-1][0].isoformat(), signal=_signal(chg, up, down), weight=weight,
                                     rule=f"{days}-day change: > {up:+g}{unit} tightening, < {down:+g}{unit} easing"))
        else:
            gaps.append(label)

    _chg_rule("NFCI", "Chicago Fed NFCI", 28, 1, 0.10, -0.10, "pts")
    _chg_rule("BAMLH0A0HYM2", "HY OAS", 30, 100, 50, -40, "bp", 1.0, "{:.2f}%")
    _chg_rule("BAMLC0A0CM", "IG OAS", 30, 100, 15, -10, "bp", 0.5, "{:.2f}%")
    usd = d.raw("DTWEXBGS")
    ago = _value_ago(usd, 30)
    if usd and ago:
        pct = (usd[-1][1] / ago[1] - 1) * 100
        ev.append(RegimeEvidence(indicator="US dollar (trade-weighted)",
                                 display=f"{pct:+.1f}% over 30d (Fed broad index vs 26 currencies, {usd[-1][1]:.1f}; Jan 2006 = 100)",
                                 as_of=usd[-1][0].isoformat(), signal=_signal(pct, 1.5, -1.5), weight=0.5,
                                 rule="30-day change: > +1.5% tightening (stronger dollar), < -1.5% easing"))
    else:
        gaps.append("US dollar (trade-weighted)")
    _chg_rule("DFII10", "10y real yield", 30, 100, 25, -25, "bp", 0.5, "{:.2f}%")
    vix = d.raw("VIXCLS")
    if vix:
        v = vix[-1][1]
        ev.append(RegimeEvidence(indicator="VIX", display=f"{v:.1f}", as_of=vix[-1][0].isoformat(),
                                 signal=1 if v > 25 else (-1 if v < 15 else 0), weight=0.5,
                                 rule="level: > 25 tightening, < 15 easing"))
    else:
        gaps.append("VIX")
    return _finish("financial_conditions", ev, gaps, ("tightening", "neutral", "easing"), 3,
                   "Weighted vote of changes in broad financial-conditions, credit, dollar and real-yield measures (US).")


def assess(specs: list[IndicatorSpec], series: dict[str, SeriesData]) -> MacroState:
    d = _Data(specs, series)
    dims = [growth(d), inflation(d), monetary_policy(d), financial_conditions(d)]
    names = {"growth": "Growth", "inflation": "Inflation", "monetary_policy": "Monetary policy", "financial_conditions": "Financial conditions"}
    summary = " · ".join(f"{names[x.dimension]}: {x.state}" for x in dims)
    return MacroState(generated_at=utc_now(), dimensions=dims, summary=summary)
