import { useMemo, useState } from 'react'

import { EventItem, ReleaseTable, regionName } from '../components/domain'
import { Card, Disabled, Empty, Ext, Importance, ProvenanceBadge, RegionTag, SubTitle } from '../components/ui'
import { fmtChange, fmtET, TOPIC_NAMES } from '../lib/format'
import type { Bundle, EventFull } from '../types'

const sel = 'rounded-md border border-line bg-surface px-2 py-1.5 text-sm text-ink'

export function EventsPage({ b }: { b: Bundle }) {
  const all = b.events.events
  const [region, setRegion] = useState('all')
  const [topic, setTopic] = useState('all')
  const [kind, setKind] = useState('all')
  const [sort, setSort] = useState<'newest' | 'importance'>('newest')
  const regions = useMemo(() => [...new Set(all.map((e) => e.region))].sort(), [all])
  const topics = useMemo(() => [...new Set(all.flatMap((e) => e.topics.slice(0, 1)))].sort(), [all])
  const list = useMemo(() => {
    const f = all.filter((e) => (region === 'all' || e.region === region) && (topic === 'all' || e.topics[0] === topic) && (kind === 'all' || e.kind === kind))
    return sort === 'importance' ? [...f].sort((a, c) => c.importance - a.importance) : f
  }, [all, region, topic, kind, sort])
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Filters">
        <select className={sel} value={sort} onChange={(e) => setSort(e.target.value as 'newest' | 'importance')} aria-label="Sort">
          <option value="newest">Newest first</option>
          <option value="importance">Most important</option>
        </select>
        <select className={sel} value={region} onChange={(e) => setRegion(e.target.value)} aria-label="Region">
          <option value="all">All regions</option>
          {regions.map((r) => <option key={r} value={r}>{regionName(r)}</option>)}
        </select>
        <select className={sel} value={topic} onChange={(e) => setTopic(e.target.value)} aria-label="Topic">
          <option value="all">All topics</option>
          {topics.map((t) => <option key={t} value={t}>{TOPIC_NAMES[t] ?? t}</option>)}
        </select>
        <select className={sel} value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Kind">
          <option value="all">News & data</option>
          <option value="data_release">Official data releases</option>
          <option value="news">News</option>
        </select>
        <span className="text-xs text-muted">{list.length} of {all.length} events · last 7 days</span>
      </div>
      <Card>
        {list.length ? <ul>{list.map((e) => <EventItem key={e.id} ev={e} />)}</ul> : <Empty>No events match these filters.</Empty>}
      </Card>
    </div>
  )
}

export function EventDetailPage({ b, id }: { b: Bundle; id: string }) {
  const ev: EventFull | undefined = b.events.events.find((e) => e.id === id)
  if (!ev) return <Card><Empty>This event is no longer in the 7-day window. <a href="#/events" className="underline">Back to events</a></Empty></Card>
  const a = ev.analysis?.output
  const aiMeta = ev.analysis ? `${ev.analysis.model} · ${fmtET(ev.analysis.generated_at)}` : ''
  const itemRef = (refId: string) => {
    const i = ev.items.findIndex((x) => x.id === refId)
    if (i >= 0) return `[${i + 1}]`
    return ev.releases.some((r) => r.id === refId) ? '[data]' : ''
  }
  return (
    <div className="space-y-4">
      <a href="#/events" className="text-xs text-ink-2 underline decoration-line underline-offset-2">← All events</a>
      <Card>
        <div className="mb-2 flex flex-wrap items-center gap-2 text-[11px] text-muted">
          <RegionTag region={ev.region} />
          <span>{ev.topics.slice(0, 3).map((t) => TOPIC_NAMES[t] ?? t).join(' · ')}</span>
          <span>· first published {fmtET(ev.first_published_at)}</span>
          <span>· {ev.source_count} source{ev.source_count === 1 ? '' : 's'}</span>
          <Importance value={ev.importance} reasons={ev.importance_reasons} />
        </div>
        <h1 className="text-xl font-semibold leading-snug text-ink">{ev.title}</h1>
        {a && <p className="mt-2 text-sm text-ink-2"><ProvenanceBadge kind="ai" /> <span className="ml-1">{a.summary}</span></p>}
        <details className="mt-2 text-xs text-muted">
          <summary className="cursor-pointer">Why this ranks here</summary>
          <ul className="mt-1 list-disc pl-5">{ev.importance_reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
        </details>
      </Card>

      <Card title="A · What happened" aside={<span className="flex gap-1">{ev.releases.length > 0 && <ProvenanceBadge kind="official" />}<ProvenanceBadge kind="fact" /></span>}>
        {ev.releases.length > 0 && <div className="mb-3"><ReleaseTable releases={ev.releases} /></div>}
        {ev.items.length > 0 ? (
          <ol className="space-y-2 text-sm">
            {ev.items.map((it, i) => (
              <li key={it.id} className="flex gap-2">
                <span className="tabular w-6 shrink-0 text-right text-xs text-muted">[{i + 1}]</span>
                <div>
                  <Ext href={it.url} className="font-medium text-ink">{it.title}</Ext>
                  <div className="text-[11px] text-muted">
                    {it.source_name}{it.source_kind === 'official' ? ' (official)' : ''} · {it.published_estimated ? 'time not given; collected ' + fmtET(it.collected_at) : fmtET(it.published_at)}
                  </div>
                  {it.summary && <p className="mt-0.5 text-xs text-ink-2">“{it.summary}” <span className="text-muted">— {it.source_name}</span></p>}
                </div>
              </li>
            ))}
          </ol>
        ) : !ev.releases.length && <Empty>No sources.</Empty>}
        {a && a.facts.length > 0 && (
          <>
            <SubTitle aside={<ProvenanceBadge kind="ai" />}>Key facts as summarised by the model (cited)</SubTitle>
            <ul className="list-disc space-y-1 pl-5 text-sm text-ink">{a.facts.map((f, i) => <li key={i}>{f.text} <span className="text-xs text-muted">{f.refs.map(itemRef).join(' ')}</span></li>)}</ul>
          </>
        )}
      </Card>

      <Card title="B · What was expected" aside={<ProvenanceBadge kind="consensus" />}>
        {ev.releases.length > 0 ? (
          <ul className="space-y-1 text-sm text-ink">
            {ev.releases.map((r) => (
              <li key={r.id}>
                <span className="font-medium">{r.short}:</span>{' '}
                {r.consensus_display ? <>consensus {r.consensus_display} <span className="text-xs text-muted">({r.consensus_source})</span>; actual {r.actual_display} → {r.surprise_display ?? 'n/a'}</> : <span className="text-ink-2">{r.consensus_note || 'No reliable consensus available.'}</span>}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-ink-2">No scheduled release with a published forecast is attached to this event, so there is no consensus to compare against.</p>
        )}
        {a?.expectations && <p className="mt-2 text-sm text-ink-2"><ProvenanceBadge kind="ai" /> <span className="ml-1">{a.expectations}</span></p>}
      </Card>

      <Card title="C · What it means economically" aside={a ? <span className="inline-flex items-center gap-2"><ProvenanceBadge kind="ai" />{aiMeta}</span> : null}>
        {a ? (
          <div className="space-y-3 text-sm">
            <ul className="space-y-2">
              {a.economic_interpretation.map((x, i) => (
                <li key={i}><span className="font-medium capitalize text-ink">{x.dimension.replace('_', ' ')}:</span> <span className="text-ink">{x.assessment}</span><div className="text-xs text-ink-2">{x.reasoning}</div></li>
              ))}
            </ul>
            <p className="text-ink-2"><span className="font-medium text-ink">Narrative: {a.narrative_effect}.</span> {a.narrative_explanation}</p>
          </div>
        ) : <Disabled what="Economic interpretation" />}
      </Card>

      <Card title="D · Potential market impact" aside={a ? <ProvenanceBadge kind="ai_impact" /> : null}>
        {a ? (
          <div className="-mx-1 overflow-x-auto">
            <table className="w-full min-w-[560px] text-sm">
              <thead><tr className="text-left text-[11px] uppercase tracking-wide text-muted"><th className="py-1 pl-1 font-medium">Asset</th><th className="font-medium">Direction</th><th className="font-medium">Strength</th><th className="font-medium">Confidence</th><th className="font-medium">Horizon</th><th className="pr-1 font-medium">Mechanism</th></tr></thead>
              <tbody>
                {a.market_impacts.map((m, i) => (
                  <tr key={i} className="border-t border-line align-top">
                    <td className="py-2 pl-1 font-medium text-ink">{m.instrument || m.asset.replaceAll('_', ' ')}</td>
                    <td className="py-2">{m.direction}</td><td className="py-2">{m.strength}</td><td className="py-2">{m.confidence}</td><td className="py-2">{m.horizon}</td>
                    <td className="py-2 pr-1 text-xs text-ink-2">{m.mechanism}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {a.alternative_scenarios.length > 0 && (
              <>
                <SubTitle>Alternative scenarios</SubTitle>
                <ul className="list-disc space-y-1 pl-5 text-sm">{a.alternative_scenarios.map((s, i) => <li key={i}><span className="font-medium">{s.scenario}</span> — <span className="text-ink-2">{s.implications}</span></li>)}</ul>
              </>
            )}
            <p className="mt-2 text-[11px] text-muted">Directional and qualitative by design — no point forecasts or probabilities.</p>
          </div>
        ) : <Disabled what="Potential market impact" />}
      </Card>

      <Card title="E · What markets actually did" aside={<ProvenanceBadge kind="observed" />}>
        {ev.observed_reaction ? (
          <div>
            <p className="mb-2 text-xs text-ink-2">{ev.observed_reaction.window} · {ev.observed_reaction.final ? 'final' : 'provisional (session not closed)'}</p>
            <div className="-mx-1 overflow-x-auto">
              <table className="w-full min-w-[460px] text-sm">
                <thead><tr className="text-left text-[11px] uppercase tracking-wide text-muted"><th className="py-1 pl-1 font-medium">Instrument</th><th className="text-right font-medium">Change</th><th className="pl-3 font-medium">Window</th><th className="pr-1 font-medium">Source</th></tr></thead>
                <tbody>
                  {ev.observed_reaction.moves.map((m) => (
                    <tr key={m.instrument_id} className="border-t border-line">
                      <td className="py-1.5 pl-1 text-ink">{m.label}</td>
                      <td className="tabular py-1.5 text-right font-medium text-ink">{fmtChange(m.change, m.change_units)}</td>
                      <td className="py-1.5 pl-3 text-xs text-ink-2">{m.start_label} → {m.end_label}</td>
                      <td className="py-1.5 pr-1 text-xs text-muted">{m.source}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ul className="mt-2 list-disc pl-5 text-[11px] text-muted">{ev.observed_reaction.caveats.map((c, i) => <li key={i}>{c}</li>)}</ul>
            {a && <p className="mt-2 text-sm text-ink-2"><ProvenanceBadge kind="ai" /> <span className="ml-1"><span className="font-medium text-ink">{a.reaction_consistency.replaceAll('_', ' ')}:</span> {a.reaction_explanation}</span></p>}
          </div>
        ) : (
          <p className="text-sm text-ink-2">No reaction window: only official data releases and central-bank decisions have a precise timestamp to measure from. See the <a href="#/markets" className="underline">markets dashboard</a> for current levels.</p>
        )}
      </Card>

      <Card title="F · What to watch next" aside={a ? <ProvenanceBadge kind="ai" /> : null}>
        {a ? (
          <div className="grid gap-4 text-sm sm:grid-cols-3">
            <div><SubTitle>Upcoming</SubTitle><ul className="list-disc space-y-1 pl-5">{a.watch_next.map((x, i) => <li key={i}>{x}</li>)}</ul></div>
            <div><SubTitle>Would invalidate this view</SubTitle><ul className="list-disc space-y-1 pl-5">{a.invalidation_triggers.map((x, i) => <li key={i}>{x}</li>)}</ul></div>
            <div><SubTitle>Key uncertainties</SubTitle><ul className="list-disc space-y-1 pl-5">{a.key_uncertainties.map((x, i) => <li key={i}>{x}</li>)}</ul></div>
          </div>
        ) : (
          <p className="text-sm text-ink-2">See the <a href="#/calendar" className="underline">calendar</a> for upcoming releases and central-bank meetings.</p>
        )}
      </Card>
    </div>
  )
}
