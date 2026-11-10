import { useState } from 'react'

import { ago, arrow, dayAge, etYmd, fmtChange, fmtDay, fmtET, fmtTimeET, fmtValue, REGION_NAMES, releasedLabel, shortAsOf, TOPIC_NAMES } from '../lib/format'
import { eventHref } from '../lib/router'
import type { CalendarRow, EquitySummary, EventCard, PolicyDecision, Quote, RegimeDimension, Release } from '../types'
import { Sparkline } from './Sparkline'
import { Empty, Ext, Importance, ProvenanceBadge, RegionTag, StaleBadge, SubTitle } from './ui'

// ── Markets ──────────────────────────────────────────────────────────────────

export function QuoteTable({ quotes, compact = false }: { quotes: Quote[]; compact?: boolean }) {
  return (
    <div className="-mx-1 overflow-x-auto">
      <table className={`w-full border-collapse text-sm ${compact ? '' : 'min-w-[300px]'}`}>
        <thead className="sr-only">
          <tr><th>Instrument</th><th>Level</th><th>Change vs prior close</th><th>Trend</th><th>As of / source</th></tr>
        </thead>
        <tbody>
          {quotes.map((q) => (
            <tr key={q.id} className="border-t border-line first:border-t-0" title={compact ? `${q.source} · ${q.as_of_label}` : undefined}>
              <td className="py-2 pl-1 pr-2 align-top">
                <div className="font-medium leading-tight text-ink">{q.label}</div>
                {compact ? (
                  <div className="text-[10px] text-muted">{shortAsOf(q.as_of, q.kind === 'intraday')}{q.kind === 'intraday' ? ' · delayed' : q.kind === 'eod' ? ' · close' : ''}</div>
                ) : (
                  <div className="text-[11px] text-muted">{q.source}{q.note ? ` · ${q.note}` : ''}</div>
                )}
                {compact && <StaleBadge stale={q.stale} />}
              </td>
              <td className="tabular whitespace-nowrap py-2 pr-2 text-right align-top font-medium text-ink">{fmtValue(q.value, q.units, q.decimals)}</td>
              <td className="tabular whitespace-nowrap py-2 pr-2 text-right align-top text-ink-2">
                <span aria-hidden className="mr-0.5 text-[10px] text-muted">{arrow(q.change)}</span>
                {fmtChange(q.change, q.change_units)}
              </td>
              <td className={`py-2 align-middle ${compact ? 'hidden pr-1 xl:table-cell' : 'hidden pr-2 sm:table-cell'}`}>
                <Sparkline points={q.history.slice(-60)} label={q.label} format={(v) => fmtValue(v, q.units, q.decimals)} width={compact ? 64 : 112} />
              </td>
              {!compact && (
                <td className="py-2 pr-1 text-right align-top text-[11px] text-muted">
                  <div>{q.as_of_label}</div>
                  <StaleBadge stale={q.stale} />
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Events ───────────────────────────────────────────────────────────────────

export function EventItem({ ev }: { ev: EventCard }) {
  return (
    <li className="border-t border-line py-3 first:border-t-0">
      <a href={eventHref(ev.id)} className="group block">
        <div className="mb-1 flex flex-wrap items-center gap-2 text-[11px] text-muted">
          <RegionTag region={ev.region} />
          {ev.kind === 'data_release' ? <ProvenanceBadge kind="official" /> : null}
          <span>{ev.topics.slice(0, 2).map((t) => TOPIC_NAMES[t] ?? t).join(' · ')}</span>
          <span>·</span>
          <span>{fmtET(ev.last_published_at ?? ev.first_seen_at)}</span>
          <Importance value={ev.importance} reasons={ev.importance_reasons} />
        </div>
        <div className="font-medium leading-snug text-ink group-hover:underline">{ev.title}</div>
        {ev.kind === 'data_release' && ev.released_at && (
          <div className="mt-0.5 text-xs font-medium text-ink-2">{releasedLabel(ev.released_at)}</div>
        )}
        <div className="mt-0.5 text-xs text-ink-2">
          {ev.lead_source}
          {ev.source_count > 1 ? ` + ${ev.source_count - 1} more source${ev.source_count > 2 ? 's' : ''}` : ''}
          {ev.analysis_status === 'done' ? ' · AI analysis available' : ''}
        </div>
      </a>
    </li>
  )
}

// ── Official releases ────────────────────────────────────────────────────────

export function ReleaseTable({ releases }: { releases: Release[] }) {
  if (!releases.length) return <Empty>No official data releases in this window.</Empty>
  return (
    <>
      <ul className="space-y-2 sm:hidden">
        {releases.map((r) => (
          <li key={r.id} className="border-t border-line pt-2 first:border-t-0 first:pt-0">
            <div className="font-medium text-ink">{r.name} <span className="text-xs font-normal text-muted">· {r.period_label}</span></div>
            <dl className="tabular mt-1 grid grid-cols-4 gap-1 text-xs">
              <div><dt className="text-muted">Actual</dt><dd className="font-semibold text-ink">{r.actual_display}</dd></div>
              <div><dt className="text-muted">Consensus</dt><dd className="text-ink-2" title={r.consensus_source ?? r.consensus_note}>{r.consensus_display ?? 'n/a'}</dd></div>
              <div><dt className="text-muted">Surprise</dt><dd className="text-ink-2">{r.surprise_display ?? '—'}</dd></div>
              <div><dt className="text-muted">Previous</dt><dd className="text-ink-2">{r.previous_display ?? '—'}</dd></div>
            </dl>
            <div className="mt-1 text-xs font-medium text-ink-2">{releasedLabel(r.release_time)}</div>
            <div className="mt-0.5 text-[10px] text-muted">
              <Ext href={r.source_url}>{r.source_name}</Ext>
              {r.consensus_source ? ` · consensus: ${r.consensus_source}` : ''}
            </div>
          </li>
        ))}
      </ul>
    <div className="-mx-1 hidden overflow-x-auto sm:block">
      <table className="w-full min-w-[620px] border-collapse text-sm">
        <thead>
          <tr className="text-left text-[11px] uppercase tracking-wide text-muted">
            <th className="py-1 pl-1 font-medium">Indicator</th>
            <th className="py-1 pl-3 font-medium">Released</th>
            <th className="py-1 pl-3 text-right font-medium">Actual</th>
            <th className="py-1 pl-3 text-right font-medium">Consensus</th>
            <th className="py-1 pl-3 text-right font-medium">Surprise</th>
            <th className="py-1 pl-3 pr-1 text-right font-medium">Previous</th>
          </tr>
        </thead>
        <tbody>
          {releases.map((r) => (
            <tr key={r.id} className="border-t border-line align-top">
              <td className="py-2 pl-1">
                <div className="font-medium text-ink">{r.name}</div>
                <div className="text-[11px] text-muted">
                  {r.period_label} · <Ext href={r.source_url}>{r.source_name}</Ext>
                </div>
              </td>
              <td className="py-2 pl-3 text-xs text-ink-2">
                <div className="whitespace-nowrap">{r.release_time ? `${fmtDay(etYmd(new Date(r.release_time)))}, ${fmtTimeET(r.release_time)}` : 'unknown'}</div>
                <div className="text-[11px] text-muted">{dayAge(r.release_time)}</div>
              </td>
              <td className="tabular py-2 pl-3 text-right font-semibold text-ink">{r.actual_display}</td>
              <td className="tabular py-2 pl-3 text-right text-ink-2">
                {r.consensus_display ? (
                  <span title={r.consensus_source ?? ''}>{r.consensus_display}<div className="text-[10px] text-muted">{r.consensus_source?.replace(' calendar (forecast)', ' forecast')}</div></span>
                ) : (
                  <span className="text-[11px] text-muted" title={r.consensus_note}>unavailable</span>
                )}
              </td>
              <td className="tabular py-2 pl-3 text-right text-ink-2">{r.surprise_display ?? '—'}</td>
              <td className="tabular py-2 pl-3 pr-1 text-right text-ink-2">
                {r.previous_display ?? '—'}
                {r.previous_first_print_display && r.previous_first_print_display !== r.previous_display && (
                  <div className="text-[10px] text-muted">first print {r.previous_first_print_display}</div>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
    </>
  )
}

// ── Calendar ─────────────────────────────────────────────────────────────────

const IMP_DOTS: Record<string, string> = { high: '●●●', medium: '●●○', low: '●○○' }

export function CalendarRowView({ row }: { row: CalendarRow }) {
  const fieldLines = row.lines.filter((l) => l.consensus || l.previous || l.actual)
  return (
    <li className="grid grid-cols-[4.5rem_1fr] gap-x-3 border-t border-line py-2.5 first:border-t-0 sm:grid-cols-[5.5rem_1fr]">
      <div className="text-xs text-ink-2">
        <div className="tabular">{row.all_day || !row.scheduled_at ? 'All day' : fmtTimeET(row.scheduled_at)}</div>
        <div className="mt-0.5 flex items-center gap-1">
          <span className="rounded border border-line px-1 text-[10px] font-medium">{row.country}</span>
        </div>
      </div>
      <div>
        <div className="flex flex-wrap items-baseline gap-x-2">
          <span className="font-medium text-ink">{row.title}</span>
          <span className="text-[10px] tracking-wider text-muted" title={`${row.importance} importance`} aria-label={`${row.importance} importance`}>{IMP_DOTS[row.importance]}</span>
          {row.status === 'released' && <span className="text-[11px] text-ink-2">· released</span>}
        </div>
        {fieldLines.length > 0 && (
          <ul className="mt-1 space-y-0.5 text-xs text-ink-2">
            {fieldLines.map((l, i) => (
              <li key={i} className="tabular">
                {row.lines.length > 1 && <span className="text-muted">{l.title}: </span>}
                {l.actual && <span className="font-semibold text-ink">Actual {l.actual} </span>}
                {l.consensus ? <span title={l.consensus_source ?? ''}>· Consensus {l.consensus} </span> : <span className="text-muted">· Consensus n/a </span>}
                {l.previous && <span>· Previous {l.previous}</span>}
              </li>
            ))}
          </ul>
        )}
        <div className="mt-0.5 text-[10px] text-muted">Source: {row.sources.join(', ')}</div>
      </div>
    </li>
  )
}

export function CalendarList({ rows }: { rows: CalendarRow[] }) {
  if (!rows.length) return <Empty>Nothing scheduled.</Empty>
  const byDay = new Map<string, CalendarRow[]>()
  for (const r of rows) byDay.set(r.date, [...(byDay.get(r.date) ?? []), r])
  return (
    <div className="space-y-4">
      {[...byDay.entries()].map(([day, list]) => (
        <div key={day}>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-2">{fmtDay(day)}</h3>
          <ul>{list.map((r) => <CalendarRowView key={r.key} row={r} />)}</ul>
        </div>
      ))}
    </div>
  )
}

// ── Macro regime ─────────────────────────────────────────────────────────────

const DIM_NAMES: Record<string, string> = {
  growth: 'Growth', inflation: 'Inflation', monetary_policy: 'Monetary policy', financial_conditions: 'Financial conditions',
}
const ENDS: Record<string, [string, string]> = {
  growth: ['slowing', 'accelerating'], inflation: ['cooling', 'accelerating'],
  financial_conditions: ['easing', 'tightening'], monetary_policy: ['easing', 'tightening'],
}

function stateGlyph(dim: string, state: string): string {
  const up = ['accelerating', 'tightening', 'restrictive']
  const down = ['slowing', 'cooling', 'easing', 'accommodative']
  if (up.includes(state)) return dim === 'financial_conditions' || dim === 'monetary_policy' ? '▲' : '↗'
  if (down.includes(state)) return dim === 'financial_conditions' || dim === 'monetary_policy' ? '▼' : '↘'
  return '→'
}

export function RegimeTile({ d }: { d: RegimeDimension }) {
  const [open, setOpen] = useState(false)
  const [lo, hi] = ENDS[d.dimension]
  const pos = d.score === null ? null : ((d.score + 1) / 2) * 100
  return (
    <div className="rounded-lg border border-line p-3">
      <div className="text-xs text-ink-2">{DIM_NAMES[d.dimension]}</div>
      <div className="mt-0.5 flex items-baseline gap-1.5 text-lg font-semibold capitalize text-ink">
        <span aria-hidden className="text-sm text-muted">{stateGlyph(d.dimension, d.state)}</span>
        {d.state}
      </div>
      {pos !== null && (
        <div className="mt-2" aria-label={`Rule score ${d.score} on a scale from −1 (${lo}) to +1 (${hi})`}>
          <div className="relative h-1 rounded-full bg-grid">
            <span className="absolute -top-1 h-3 w-px bg-axis" style={{ left: '50%' }} />
            <span className="absolute -top-[3px] h-2.5 w-2.5 -translate-x-1/2 rounded-full border-2 border-surface bg-ink-2" style={{ left: `${pos}%` }} />
          </div>
          <div className="mt-1 flex justify-between text-[10px] text-muted"><span>{lo}</span><span>{hi}</span></div>
        </div>
      )}
      <button type="button" onClick={() => setOpen(!open)} className="mt-2 text-[11px] text-ink-2 underline decoration-line underline-offset-2" aria-expanded={open}>
        {open ? 'Hide evidence' : `Evidence (${d.evidence.length})`}
      </button>
      {open && (
        <ul className="mt-2 space-y-1.5 text-xs text-ink-2">
          {d.evidence.map((e, i) => (
            <li key={i} title={e.rule}>
              <span aria-hidden className="mr-1 text-muted">{e.signal > 0 ? '+' : e.signal < 0 ? '−' : '0'}</span>
              <span className="font-medium text-ink">{e.indicator}</span>: {e.display} <span className="text-muted">({e.as_of})</span>
              <div className="text-[10px] text-muted">Rule: {e.rule}{e.weight !== 1 ? ` · weight ${e.weight}` : ''}</div>
            </li>
          ))}
          {d.data_gaps.length > 0 && <li className="text-muted">Data gaps: {d.data_gaps.join(', ')}</li>}
          <li className="text-[10px] text-muted">{d.method}</li>
        </ul>
      )}
    </div>
  )
}

// ── Today ────────────────────────────────────────────────────────────────────

export function PolicyDecisionView({ d }: { d: PolicyDecision }) {
  return (
    <li className="border-t border-line py-2 first:border-t-0">
      <div className="flex flex-wrap items-baseline gap-x-2">
        <span className="font-medium text-ink">{d.name}</span>
        <span className="text-xs text-ink-2">{d.status === 'done' ? fmtET(d.scheduled_at) : `later today, ${fmtTimeET(d.scheduled_at)}`}</span>
      </div>
      <ul className="mt-1 space-y-0.5 text-xs text-ink-2">
        {d.lines.filter((l) => l.consensus || l.previous || l.actual).map((l, i) => (
          <li key={i} className="tabular">
            <span className="text-muted">{l.title}: </span>
            {l.actual && <span className="font-semibold text-ink">Actual {l.actual} · </span>}
            {l.consensus ? <span title={l.consensus_source ?? ''}>Consensus {l.consensus}</span> : <span className="text-muted">Consensus n/a</span>}
            {l.previous && <span> · Previous {l.previous}</span>}
          </li>
        ))}
        {d.outcome && <li><span className="font-semibold text-ink">{d.outcome.text}</span> <span className="text-muted">({d.outcome.source})</span></li>}
        {d.coverage && (
          <li>
            Coverage: <a className="underline decoration-line underline-offset-2" href={eventHref(d.coverage.event_id)}>{d.coverage.title}</a>
            <span className="text-muted"> · {d.coverage.sources} source{d.coverage.sources === 1 ? '' : 's'}</span>
          </li>
        )}
      </ul>
    </li>
  )
}

export function EquityPanel({ eq }: { eq: EquitySummary | null }) {
  if (!eq || !eq.indices.length) return <Empty>US index data unavailable.</Empty>
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-ink-2">
        <ProvenanceBadge kind="observed" />
        <span>{eq.session_label}</span>
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-5">
        {eq.indices.map((m) => (
          <div key={m.id} className="rounded-lg border border-line px-3 py-2">
            <div className="text-[11px] text-ink-2">{m.label}</div>
            <div className="tabular text-base font-semibold text-ink">
              <span aria-hidden className="mr-0.5 text-[10px] text-muted">{arrow(m.change_pct)}</span>
              {fmtChange(m.change_pct, '%')}
            </div>
            <div className="tabular text-[11px] text-muted">{m.value?.toLocaleString('en-US', { maximumFractionDigits: 0 })}</div>
          </div>
        ))}
        {eq.vix !== null && (
          <div className="rounded-lg border border-line px-3 py-2">
            <div className="text-[11px] text-ink-2">VIX</div>
            <div className="tabular text-base font-semibold text-ink">{eq.vix.toFixed(1)}</div>
            <div className="tabular text-[11px] text-muted">{fmtChange(eq.vix_change, 'pts')} pts</div>
          </div>
        )}
      </div>
      <p className="mt-2 text-sm text-ink">
        Sentiment gauge: <span className="font-semibold">{eq.sentiment}</span>
        <span className="text-xs text-muted" title={eq.sentiment_rule}> (rule-based on S&amp;P 500 and VIX moves — not a forecast)</span>
      </p>
      {eq.breadth_note && <p className="mt-1 text-xs text-ink-2">Breadth: {eq.breadth_note}</p>}
      {eq.headlines.length > 0 && (
        <>
          <div className="mt-3 flex items-center gap-2"><ProvenanceBadge kind="fact" /><span className="text-xs text-ink-2">Market headlines</span></div>
          <ul className="mt-1 space-y-1 text-sm">
            {eq.headlines.map((h) => (
              <li key={h.url}>
                <Ext href={h.url} className="text-ink">{h.title}</Ext>{' '}
                <span className="text-xs text-muted">— {h.source_name}, {ago(h.published_at)}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}

export function TodayPanel({ decisions, releases, equities }: { decisions: PolicyDecision[]; releases: Release[]; equities: EquitySummary | null }) {
  return (
    <div>
      <SubTitle aside={<ProvenanceBadge kind="official" />}>Central-bank decisions</SubTitle>
      {decisions.length ? <ul>{decisions.map((d) => <PolicyDecisionView key={d.family + d.date} d={d} />)}</ul> : <Empty>No central-bank decisions in the last 24 hours or later today.</Empty>}
      <SubTitle aside={<span className="flex gap-1"><ProvenanceBadge kind="official" /><ProvenanceBadge kind="consensus" /></span>}>Key data releases</SubTitle>
      <ReleaseTable releases={releases} />
      <SubTitle>US stock market</SubTitle>
      <EquityPanel eq={equities} />
    </div>
  )
}

export function regionName(r: string) {
  return REGION_NAMES[r] ?? r
}
