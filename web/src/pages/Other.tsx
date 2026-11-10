import { useState } from 'react'

import { CalendarList, QuoteTable } from '../components/domain'
import { Sparkline } from '../components/Sparkline'
import { Card, Empty, Ext, FreshDot, ProvenanceBadge, StaleBadge, SubTitle, type Provenance } from '../components/ui'
import { ago, etYmd, fmtDay, fmtET, fmtNum } from '../lib/format'
import { eventHref } from '../lib/router'
import type { Bundle, IndicatorReading } from '../types'

export function CalendarPage({ b }: { b: Bundle }) {
  const [view, setView] = useState<'upcoming' | 'past'>('upcoming')
  const today = etYmd()
  const rows = b.calendar.rows.filter((r) => (view === 'upcoming' ? r.date >= today && r.status !== 'past' || (r.date === today) : r.date <= today && r.status !== 'upcoming'))
  const shown = view === 'past' ? [...rows].reverse() : rows
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {(['upcoming', 'past'] as const).map((v) => (
          <button key={v} type="button" onClick={() => setView(v)} aria-pressed={view === v} className={`rounded-md border border-line px-3 py-1.5 text-sm ${view === v ? 'bg-wash font-semibold text-ink' : 'text-ink-2'}`}>
            {v === 'upcoming' ? 'Upcoming (3 weeks)' : 'Past week'}
          </button>
        ))}
        <span className="flex items-center gap-1 text-xs text-muted"><ProvenanceBadge kind="consensus" /> published forecasts with their source named; actuals only from official data</span>
      </div>
      <Card>
        <CalendarList rows={shown} />
        <p className="mt-3 text-[11px] text-muted">
          Coverage: US high & medium importance; euro area, UK, Japan and China high importance; other G10 central-bank decisions.
          Times in US Eastern. Each row names its source.
        </p>
      </Card>
    </div>
  )
}

export function MarketsPage({ b }: { b: Bundle }) {
  return (
    <div className="space-y-4">
      <p className="flex flex-wrap items-center gap-2 text-xs text-ink-2">
        <ProvenanceBadge kind="observed" />
        Snapshot {fmtET(b.markets.snapshot_taken_at)} ({ago(b.markets.snapshot_taken_at)}). Treasury yields are official end-of-day; intraday quotes are delayed. Yields and spreads change in basis points.
      </p>
      <div className="grid gap-4 lg:grid-cols-2">
        {b.markets.groups.map((g) => (
          <Card key={g.id} title={g.label}>
            <QuoteTable quotes={g.quotes} />
          </Card>
        ))}
      </div>
    </div>
  )
}

function IndicatorTable({ rows }: { rows: IndicatorReading[] }) {
  return (
    <div className="-mx-1 overflow-x-auto">
      <table className="w-full min-w-[480px] text-sm">
        <thead>
          <tr className="text-left text-[11px] uppercase tracking-wide text-muted">
            <th className="py-1 pl-1 font-medium">Indicator</th><th className="text-right font-medium">Latest</th><th className="text-right font-medium">Previous</th><th className="hidden pl-3 font-medium sm:table-cell">Trend</th><th className="pr-1 text-right font-medium">Period / released</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-t border-line align-top">
              <td className="py-2 pl-1">
                <div className="font-medium text-ink">{r.short}</div>
                <div className="text-[11px] text-muted"><Ext href={r.source_url}>{r.source}</Ext>{r.notes ? ` · ${r.notes}` : ''}</div>
              </td>
              <td className="tabular py-2 text-right font-semibold text-ink">{r.latest_display}</td>
              <td className="tabular py-2 text-right text-ink-2">{r.previous_display}</td>
              <td className="hidden py-2 pl-3 align-middle sm:table-cell">
                <Sparkline points={r.history} label={r.name} format={(v) => fmtNum(v, r.decimals) + (r.units.startsWith('%') ? '%' : '')} />
              </td>
              <td className="py-2 pr-1 text-right text-[11px] text-muted">
                {r.latest_label}
                {r.released && <div className="text-ink-2">released {fmtDay(r.released)}</div>}
                <div><StaleBadge stale={r.stale} reason={r.stale_reason} /></div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function EconomyPage({ b }: { b: Bundle }) {
  return (
    <div className="space-y-4">
      <p className="flex flex-wrap items-center gap-2 text-xs text-ink-2">
        <ProvenanceBadge kind="official" />
        Latest available vintage; monthly data refer to the period shown (typically published 2–6 weeks later).
      </p>
      <div className="grid gap-4 lg:grid-cols-2">
        {b.economy.groups.map((g) => (
          <Card key={g.id} title={g.label}><IndicatorTable rows={g.indicators} /></Card>
        ))}
      </div>
    </div>
  )
}

export function BriefingsPage({ b }: { b: Bundle }) {
  const list = b.briefings.briefings
  if (!list.length) return <Card><Empty>No briefings yet.</Empty></Card>
  return (
    <div className="space-y-3">
      {list.map((br, i) => (
        <details key={br.id} open={i === 0} className="rounded-xl border border-line bg-surface p-4">
          <summary className="cursor-pointer list-none">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="font-semibold text-ink">{br.content.headline}</span>
              <span className="text-xs text-muted">{br.date} · {br.mode === 'ai' ? `AI (${br.model})` : 'data-only'}</span>
            </div>
          </summary>
          <div className="mt-3 space-y-2 text-sm text-ink-2">
            {br.mode === 'ai' && <ProvenanceBadge kind="ai" />}
            <p>{br.content.overview}</p>
            {br.equities && <p><span className="font-medium text-ink">US stocks: </span>{br.mode === 'ai' && br.content.us_equity_market ? br.content.us_equity_market : br.equities.summary}</p>}
            <SubTitle>Key developments</SubTitle>
            <ul className="list-disc space-y-1 pl-5">{br.content.key_developments.map((p, j) => <li key={j}>{p.event_ids[0] ? <a className="underline decoration-line" href={eventHref(p.event_ids[0])}>{p.text}</a> : p.text}</li>)}</ul>
            <SubTitle>What changed</SubTitle>
            <p>{br.content.what_changed}</p>
            {br.data_points.length > 0 && (
              <>
                <SubTitle aside={<ProvenanceBadge kind="official" />}>Data points</SubTitle>
                <ul className="list-disc space-y-0.5 pl-5 text-xs">{br.data_points.map((d, j) => <li key={j}>{d}</li>)}</ul>
              </>
            )}
          </div>
        </details>
      ))}
    </div>
  )
}

const LEGEND: [Provenance, string][] = [
  ['fact', 'Headline and short summary from a named source, with link and timestamp.'],
  ['official', 'Statistics from official agencies (statistics offices, central banks, treasuries), with the source named.'],
  ['consensus', 'A published forecast with its source named (e.g. an economic calendar). Shown as "unavailable" when none exists — never inferred, never the previous value.'],
  ['ai', 'Model-generated interpretation (when AI is enabled). Cites the sources it was given; not a fact.'],
  ['ai_impact', 'Model-generated potential impact: direction, relative strength, confidence, horizon and mechanism — no point forecasts.'],
  ['observed', 'Measured market moves with an explicit window, timestamps and source.'],
]

export function AboutPage({ b }: { b: Bundle }) {
  const m = b.meta
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="How to read this site">
        <ul className="space-y-2 text-sm">
          {LEGEND.map(([k, t]) => <li key={k} className="flex flex-col gap-1 sm:flex-row sm:items-start sm:gap-3"><span className="shrink-0"><ProvenanceBadge kind={k} /></span><span className="text-ink-2">{t}</span></li>)}
        </ul>
        <SubTitle>Coverage</SubTitle>
        <p className="text-sm text-ink-2">US first. Other G10 economies and China appear only when something material happens there — a central-bank decision, a top-tier data release, a big market move or a major multi-outlet story.</p>
        <SubTitle>Ranking & regime</SubTitle>
        <p className="text-sm text-ink-2">Events are ranked by transparent rules (macro topic, region, source tier, release importance, capped coverage breadth) — open an event to see why it ranks where it does. The macro regime uses explicit thresholds on official data; open each tile for its evidence and rules.</p>
        <SubTitle>Update schedule</SubTitle>
        <p className="text-sm text-ink-2">{m.schedule}</p>
      </Card>
      <div className="space-y-4">
        <Card title="Last update run" aside={m.last_run ? fmtET(m.last_run.finished_at) : ''}>
          {m.last_run ? (
            <ul className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-3">
              {m.last_run.stages.map((s) => (
                <li key={s.name} title={s.detail} className="flex items-center justify-between gap-2 border-b border-line py-1">
                  <span className="text-ink">{s.name}</span>
                  <span className="text-ink-2">{s.status === 'ok' ? <span><span aria-hidden className="text-good">●</span> ok</span> : s.status === 'skipped' ? 'skipped' : <span><span aria-hidden className="text-critical">✕</span> error</span>}</span>
                </li>
              ))}
            </ul>
          ) : <Empty>No run recorded.</Empty>}
          <p className="mt-2 text-xs text-ink-2">AI analysis: {m.llm.enabled ? `on (${m.llm.model}); today ${m.llm.calls_today} calls, $${m.llm.cost_today_usd.toFixed(2)} of $${m.llm.daily_budget_usd.toFixed(2)} budget` : 'off (data-only mode)'}</p>
        </Card>
        <Card title="Sources">
          <div className="-mx-1 overflow-x-auto">
            <table className="w-full min-w-[420px] text-xs">
              <thead><tr className="text-left uppercase tracking-wide text-muted"><th className="py-1 pl-1 font-medium">Source</th><th className="font-medium">Type</th><th className="font-medium">Last fetch</th><th className="pr-1 font-medium">Status</th></tr></thead>
              <tbody>
                {b.sources.sources.map((s) => (
                  <tr key={s.id} className="border-t border-line">
                    <td className="py-1.5 pl-1"><Ext href={s.homepage} className="text-ink">{s.name}</Ext>{s.paywalled ? <span className="text-muted"> · paywalled (headlines only)</span> : null}</td>
                    <td className="text-ink-2">{s.kind}, tier {s.tier}</td>
                    <td className="text-ink-2">{ago(s.health?.last_attempt)}</td>
                    <td className="pr-1" title={s.health?.error ?? ''}><FreshDot ok={!!s.health?.ok} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-[11px] text-muted">Only titles, short feed summaries and links are stored; articles are never reproduced.</p>
        </Card>
      </div>
    </div>
  )
}
