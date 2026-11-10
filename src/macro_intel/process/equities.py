"""US stock-market snapshot for the top of the overview/briefing (deterministic).

Index levels/changes come from the market snapshot (Yahoo Finance, delayed); headlines are
attributed market-wrap items from the news store. The sentiment label is a simple documented
rule on the S&P 500 change and the VIX change — a gauge, not a forecast.
"""

from __future__ import annotations

import re
from datetime import timedelta

from macro_intel.models import EquityMarketSummary, IndexMove, MarketHeadline, MarketSnapshot
from macro_intel.process.classify import NOISE
from macro_intel.store import State
from macro_intel.timeutil import ET, to_utc, utc_now

INDEX_IDS = ["spx", "dji", "ixic", "rut"]
SENTIMENT_RULE = ("S&P 500 change vs previous close: ≤ −1.5% (or ≤ −1.0% with VIX +3pts) strongly negative; "
                  "≤ −0.5% negative; ≥ +1.5% (or ≥ +1.0% with VIX −2pts) strongly positive; ≥ +0.5% positive; "
                  "otherwise mixed / flat.")
# Broad-market headlines only: index names, "stocks" (plural), Wall Street, equities, the fear gauge.
_WRAP = re.compile(r"\b(stock market|stocks|dow|s&p( 500)?|nasdaq|wall street|equities|fear gauge|vix|russell 2000)\b", re.I)
# Single companies, sector trade ideas and advice pieces are not market-wide sentiment.
_NOT_BROAD = re.compile(
    r"\b(nvidia|apple|tesla|microsoft|amazon|meta|alphabet|google|netflix|broadcom|oracle|palantir|berkshire|"
    r"jpmorgan|goldman|ceo|shares of|you|your|says [A-Z][a-z]+ [A-Z][a-z]+$|top picks?|trade idea|stocks to)\b",
    re.I,
)
_WRAP_BOOST = re.compile(r"live updates|stock market today|dow (jumps|falls|drops|tumbles|rises|gains|slides)|"
                         r"s&p 500 (rises|falls|closes|hits)|nasdaq (falls|rises|plummets|jumps)", re.I)
_SINGLE_STOCK = re.compile(r"biggest moves|stocks to buy|shares of|earnings|\b[A-Z]{2,5}\b stock\b|ipo\b", re.I)


def sentiment(spx_pct: float | None, vix_chg: float | None) -> str:
    if spx_pct is None:
        return "unavailable"
    v = vix_chg or 0.0
    if spx_pct <= -1.5 or (spx_pct <= -1.0 and v >= 3):
        return "strongly negative"
    if spx_pct <= -0.5:
        return "negative"
    if spx_pct >= 1.5 or (spx_pct >= 1.0 and v <= -2):
        return "strongly positive"
    if spx_pct >= 0.5:
        return "positive"
    return "mixed / flat"


def _session(snap: MarketSnapshot) -> tuple[str, str]:
    q = snap.quotes.get("spx")
    if not q or q.value is None or not q.history:
        return "unknown", "No index data available"
    now_et = utc_now().astimezone(ET)
    last_day = q.history[-1][0]
    if q.as_of is not None and q.kind == "intraday":
        t = q.as_of.astimezone(ET)
        if t.date() == now_et.date() and t.hour < 16:
            return "intraday", f"Intraday, as of {t.strftime('%H:%M ET')} (delayed) — change vs previous close"
        return "closed", f"Close of {t.date().isoformat()} — change vs previous close"
    return ("pre_open" if last_day < now_et.date().isoformat() else "closed"), f"Close of {last_day} — change vs previous close"


def headlines(state: State, limit: int = 3, hours: int = 12) -> list[MarketHeadline]:
    """Fresh, attributed market-wrap headlines: recency first, with a mild boost for wrap/live pages."""
    now = utc_now()
    cut = now - timedelta(hours=hours)
    cands = []
    for it in state.items.values():
        t = to_utc(it.published_at or it.collected_at)
        if t < cut or it.source_tier > 2 or it.region not in ("US", "Global"):
            continue
        if not _WRAP.search(it.title) or NOISE.search(it.title) or _SINGLE_STOCK.search(it.title) or _NOT_BROAD.search(it.title):
            continue
        age_h = (now - t).total_seconds() / 3600.0
        boost = (1.5 if _WRAP_BOOST.search(it.title) else 0.0) + (1.0 if "market_shock" in it.concepts else 0.0)
        cands.append((boost - age_h / 2.0, it))  # a wrap page is worth ~3 h of freshness
    cands.sort(key=lambda x: x[0], reverse=True)
    out, seen_events = [], set()
    for _, it in cands:
        key = it.event_id or it.id
        if key in seen_events:
            continue
        seen_events.add(key)
        out.append(MarketHeadline(title=it.title, source_name=it.source_name, url=it.url, published_at=it.published_at))
        if len(out) >= limit:
            break
    return out


def summarize(state: State) -> EquityMarketSummary | None:
    snap = state.latest_snapshot
    if snap is None:
        return None
    s = EquityMarketSummary(generated_at=utc_now())
    s.session, s.session_label = _session(snap)
    for iid in INDEX_IDS:
        q = snap.quotes.get(iid)
        if q and q.value is not None:
            s.indices.append(IndexMove(id=iid, label=q.label, value=q.value, change_pct=q.change, as_of_label=q.as_of_label))
    vix = snap.quotes.get("vix")
    if vix and vix.value is not None:
        s.vix, s.vix_change = vix.value, vix.change
    spx, rsp = snap.quotes.get("spx"), snap.quotes.get("spx_ew")
    if spx and rsp and spx.change is not None and rsp.change is not None:
        gap = rsp.change - spx.change
        s.breadth_note = (f"Equal-weight S&P 500 {rsp.change:+.2f}% vs cap-weighted {spx.change:+.2f}% — "
                          + ("broad-based move" if abs(gap) < 0.4 else
                             "average stock outperforming the mega-caps" if gap > 0 else "move concentrated in the largest stocks"))
    spx_pct = spx.change if spx else None
    s.sentiment = sentiment(spx_pct, s.vix_change)  # type: ignore[assignment]
    s.sentiment_rule = SENTIMENT_RULE
    s.headlines = headlines(state)
    if s.indices:
        parts = ", ".join(f"{m.label} {m.change_pct:+.1f}%" for m in s.indices if m.change_pct is not None)
        vix_txt = f"; VIX {s.vix:.1f} ({s.vix_change:+.1f}pts)" if s.vix is not None and s.vix_change is not None else ""
        s.summary = f"{s.session_label}: {parts}{vix_txt}. Rule-based sentiment gauge: {s.sentiment}."
    else:
        s.summary = "US index data unavailable."
    return s
