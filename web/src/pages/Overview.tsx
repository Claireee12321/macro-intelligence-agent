import { CalendarList, EventItem, QuoteTable, RegimeTile, TodayPanel } from '../components/domain'
import { Card, Empty, ProvenanceBadge, SubTitle } from '../components/ui'
import { ago, fmtDay, fmtET } from '../lib/format'
import { eventHref } from '../lib/router'
import type { Bundle } from '../types'

export function OverviewPage({ b }: { b: Bundle }) {
  const ov = b.overview
  const br = ov.briefing
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <div className="min-w-0 space-y-4 lg:col-span-2">
        <Card title="Today" aside={`${fmtDay(ov.today_date)} · updated ${ago(ov.generated_at)}`}>
          <TodayPanel decisions={ov.today.central_bank_decisions} releases={ov.today.key_releases} equities={ov.today.us_equities} />
        </Card>

        <Card
          title="Daily briefing"
          aside={br ? <span className="inline-flex items-center gap-2">{br.mode === 'ai' ? <ProvenanceBadge kind="ai" /> : <span>Data-only</span>}{fmtET(br.generated_at)}</span> : null}
        >
          {br ? (
            <div className="space-y-3 text-sm leading-relaxed text-ink">
              <p className="text-base font-semibold">{br.content.headline}</p>
              <p className="text-ink-2">{br.content.overview}</p>
              {br.mode === 'ai' && br.content.us_equity_market && (
                <p><span className="font-medium">US stocks: </span>{br.content.us_equity_market}</p>
              )}
              {br.content.key_developments.length > 0 && (
                <>
                  <SubTitle>Key developments</SubTitle>
                  <ul className="list-disc space-y-1 pl-5">
                    {br.content.key_developments.map((p, i) => (
                      <li key={i}>{p.event_ids[0] ? <a className="underline decoration-line underline-offset-2" href={eventHref(p.event_ids[0])}>{p.text}</a> : p.text}</li>
                    ))}
                  </ul>
                </>
              )}
              <SubTitle>What changed</SubTitle>
              <p className="text-ink-2">{br.content.what_changed}</p>
              {br.content.market_implications.length > 0 && (
                <>
                  <SubTitle aside={<ProvenanceBadge kind="ai_impact" />}>Market implications</SubTitle>
                  <ul className="list-disc space-y-1 pl-5">{br.content.market_implications.map((p, i) => <li key={i}>{p.text}</li>)}</ul>
                </>
              )}
              {br.content.what_to_watch.length > 0 && (
                <>
                  <SubTitle>What to watch</SubTitle>
                  <ul className="list-disc space-y-1 pl-5 text-ink-2">{br.content.what_to_watch.slice(0, 6).map((p, i) => <li key={i}>{p.text}</li>)}</ul>
                </>
              )}
              {br.content.risks.length > 0 && (
                <>
                  <SubTitle>Risks</SubTitle>
                  <ul className="list-disc space-y-1 pl-5 text-ink-2">{br.content.risks.map((r, i) => <li key={i}>{r}</li>)}</ul>
                </>
              )}
              <a href="#/briefings" className="inline-block text-xs text-ink-2 underline decoration-line underline-offset-2">Past briefings →</a>
            </div>
          ) : (
            <Empty>No briefing yet today.</Empty>
          )}
        </Card>

        <Card title="Top developments" aside={<a href="#/events" className="underline decoration-line underline-offset-2">All events →</a>}>
          {ov.top_events.length ? <ul>{ov.top_events.map((e) => <EventItem key={e.id} ev={e} />)}</ul> : <Empty>No major developments in the last 36 hours.</Empty>}
        </Card>
      </div>

      <div className="min-w-0 space-y-4">
        <Card title="Macro regime" aside="Rule-based, US">
          {ov.macro_state ? (
            <>
              <div className="grid grid-cols-2 gap-2">
                {ov.macro_state.dimensions.map((d) => <RegimeTile key={d.dimension} d={d} />)}
              </div>
              <p className="mt-2 text-[11px] text-muted">Deterministic thresholds on official data — see <a href="#/about" className="underline">methodology</a>.</p>
            </>
          ) : (
            <Empty>Not yet assessed.</Empty>
          )}
        </Card>
        <Card title="Key markets" aside={<a href="#/markets" className="underline decoration-line underline-offset-2">All →</a>}>
          <QuoteTable quotes={ov.key_markets} compact />
        </Card>
        <Card title="Coming up" aside={<a href="#/calendar" className="underline decoration-line underline-offset-2">Calendar →</a>}>
          <CalendarList rows={ov.upcoming.slice(0, 8)} />
        </Card>
      </div>
    </div>
  )
}
