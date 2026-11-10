"""Readable Markdown digest of the exported site bundle (for review and quick checks)."""

from __future__ import annotations

import json
from pathlib import Path

from macro_intel.timeutil import ET, fmt_et


def _load(site: Path, name: str) -> dict:
    p = site / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _t(iso: str | None) -> str:
    from datetime import datetime

    return fmt_et(datetime.fromisoformat(iso)) if iso else ""


def _q(q: dict) -> str:
    v = q.get("value")
    if v is None:
        return "n/a"
    u = q["units"]
    val = f"{v:.{q['decimals']}f}%" if u == "%" else (f"{v:+.0f}bp" if u == "bp" else f"{v:,.{q['decimals']}f}")
    c = q.get("change")
    cu = q["change_units"]
    ch = "n/a" if c is None else (f"{c:+.0f}bp" if cu == "bp" else f"{c:+.2f}{'pts' if cu == 'pts' else '%'}")
    return f"{val} ({ch})"


def build_digest(site: Path, max_events: int = 25) -> str:
    meta, ov, evs = _load(site, "meta.json"), _load(site, "overview.json"), _load(site, "events.json")
    cal, mk, eco, src = _load(site, "calendar.json"), _load(site, "markets.json"), _load(site, "economy.json"), _load(site, "sources.json")
    L: list[str] = []
    L.append(f"# Macro Intelligence Agent — data digest\n")
    L.append(f"Generated {_t(meta.get('generated_at'))} · mode **{meta.get('mode')}** · sample={meta.get('is_sample')} · "
             f"FRED API key={'yes' if meta.get('fred_api') else 'no (public CSV)'}\n")
    td = ov.get("today") or {}
    L.append("## Today\n")
    L.append("**1. Central-bank decisions (last 24 h / later today)**")
    if not td.get("central_bank_decisions"):
        L.append("- None scheduled.")
    for d in td.get("central_bank_decisions", []):
        ls = "; ".join(f"{x['title']}: " + ", ".join(y for y in (f"actual {x['actual']}" if x.get('actual') else '',
                       f"forecast {x['consensus']}" if x.get('consensus') else '', f"previous {x['previous']}" if x.get('previous') else '') if y)
                       for x in d["lines"] if x.get("consensus") or x.get("previous") or x.get("actual"))
        L.append(f"- **{d['name']}** ({d['status']}, {_t(d['scheduled_at'])}) {ls}"
                 + (f" · Outcome: {d['outcome']['text']}" if d.get('outcome') else "")
                 + (f" · Coverage: {d['coverage']['title']} ({d['coverage']['sources']} sources)" if d.get('coverage') else ""))
    L.append("\n**2. Key data releases (last 24 h)**")
    if not td.get("key_releases"):
        L.append("- None.")
    for r in td.get("key_releases", []):
        L.append(f"- {r['name']} ({r['period_label']}): {r['actual_display']} vs forecast {r.get('consensus_display') or 'n/a'} — released {_t(r.get('release_time'))}")
    eq = td.get("us_equities")
    L.append("\n**3. US stock market**")
    if eq:
        L.append(f"- {eq['summary']}")
        if eq.get("breadth_note"):
            L.append(f"- Breadth: {eq['breadth_note']}")
        for h in eq.get("headlines", []):
            L.append(f"- [{h['title']}]({h['url']}) — {h['source_name']}")
    L.append("")
    ms = ov.get("macro_state")
    if ms:
        L.append("## Macro regime (deterministic)\n")
        for d in ms["dimensions"]:
            L.append(f"**{d['dimension'].replace('_', ' ').title()}: {d['state']}** (score {d.get('score')})")
            for e in d["evidence"]:
                L.append(f"- {'+' if e['signal'] > 0 else '−' if e['signal'] < 0 else '0'} {e['indicator']}: {e['display']} ({e['as_of']}) — rule: {e['rule']}")
            if d.get("data_gaps"):
                L.append(f"- data gaps: {', '.join(d['data_gaps'])}")
            L.append("")
    b = ov.get("briefing")
    if b:
        c = b["content"]
        L.append(f"## Briefing {b['id']} ({b['mode']})\n\n**{c['headline']}**\n\n{c['overview']}\n")
        L.append(f"What changed: {c['what_changed']}\n")
    L.append("## Recent official releases\n")
    rels = ov.get("recent_releases", [])
    if not rels:
        L.append("_None detected in the last 7 days (on the first run, only releases with evidence of publication in the last few days are recorded)._\n")
    for r in rels:
        L.append(f"- **{r['name']} ({r['period_label']})**: actual {r['actual_display']} · consensus "
                 f"{(r['consensus_display'] + ' [' + r['consensus_source'] + ']') if r.get('consensus_display') else 'unavailable — ' + r['consensus_note']}"
                 f" · surprise {r.get('surprise_display', 'n/a')} · previous {r['previous_display']} · released {_t(r.get('release_time'))} ({r['release_time_basis']}) · {r['source_name']}")
    L.append("\n## Events (importance ≥ 45, last 7 days, newest first)\n")
    for e in evs.get("events", [])[:max_events]:
        L.append(f"### [{e['importance']:.0f}] {e['title']}")
        L.append(f"{e['kind']} · {e['region']} · topics {', '.join(e['topics'][:3])} · {e['source_count']} source(s) · "
                 f"first published {_t(e['first_published_at'])} · analysis: {e['analysis_status']}")
        L.append(f"_Why ranked:_ {'; '.join(e['importance_reasons'])}")
        for it in e["items"][:6]:
            L.append(f"- {it['source_name']} ({_t(it['published_at'])}, rel {it['relevance']:.0f}): [{it['title']}]({it['url']})")
        for r in e["releases"]:
            L.append(f"- OFFICIAL DATA: {r['name']} {r['period_label']} = {r['actual_display']} (consensus {r.get('consensus_display') or 'unavailable'}) — released {_t(r.get('release_time'))}")
        if e.get("observed_reaction"):
            mv = "; ".join(f"{m['label']} {m['change']:+.2f}{m['change_units']}" for m in e["observed_reaction"]["moves"] if m.get("change") is not None)
            L.append(f"- OBSERVED ({'final' if e['observed_reaction']['final'] else 'provisional'}): {mv}")
        L.append("")
    L.append("## Calendar (next 7 days, high/medium)\n")
    L.append("| When (ET) | Ctry | Event | Consensus (source) | Previous | Actual |\n|---|---|---|---|---|---|")
    for r in cal.get("rows", []):
        if r["status"] != "upcoming" or r["importance"] == "low":
            continue
        for ln in r["lines"][:4]:
            L.append(f"| {_t(ln.get('scheduled_at') or r.get('scheduled_at')) or r['date']} | {r['country']} | {ln['title']} | "
                     f"{(ln['consensus'] + ' (' + ln['consensus_source'] + ')') if ln.get('consensus') else '—'} | {ln.get('previous') or '—'} | {ln.get('actual') or '—'} |")
    L.append("\n## Markets\n")
    for g in mk.get("groups", []):
        L.append(f"**{g['label']}**: " + " · ".join(f"{q['label']} {_q(q)}{' ⚠stale' if q['stale'] else ''}" for q in g["quotes"]))
        L.append("")
    L.append("## Economic indicators\n")
    for g in eco.get("groups", []):
        L.append(f"**{g['label']}**: " + " · ".join(f"{i['short']} {i['latest_display']} ({i['latest_label']}{', released ' + i['released'] if i.get('released') else ''}){' ⚠stale' if i['stale'] else ''}" for i in g["indicators"]))
        L.append("")
    L.append("## Source health\n")
    for s in src.get("sources", []):
        h = s.get("health") or {}
        L.append(f"- {'✅' if h.get('ok') else '❌'} {s['name']} (tier {s['tier']}, {s['kind']}) — fetched {h.get('fetched', 0)} {('· ' + h['error']) if h.get('error') else ''}")
    return "\n".join(L) + "\n"


def write_digest(site: Path, out: Path) -> Path:
    out.write_text(build_digest(site), encoding="utf-8")
    return out
