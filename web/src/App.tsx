import { Layout } from './components/Layout'
import { useBundle } from './lib/data'
import { useRoute } from './lib/router'
import { EventDetailPage, EventsPage } from './pages/Events'
import { AboutPage, BriefingsPage, CalendarPage, EconomyPage, MarketsPage } from './pages/Other'
import { OverviewPage } from './pages/Overview'

export default function App() {
  const state = useBundle()
  const route = useRoute()

  if (state.status === 'loading') {
    return <p className="p-6 text-sm text-ink-2">Loading the latest data…</p>
  }
  if (state.status === 'error') {
    return (
      <div className="mx-auto max-w-xl p-6 text-sm text-ink">
        <p className="font-semibold">Could not load the site data.</p>
        <p className="mt-1 text-ink-2">{state.error}</p>
        <p className="mt-2 text-ink-2">Run <code>macro-intel run</code> to produce <code>data/site/*.json</code>, then reload.</p>
      </div>
    )
  }
  const b = state.data
  return (
    <Layout meta={b.meta} route={route}>
      {route.page === 'overview' && <OverviewPage b={b} />}
      {route.page === 'events' && <EventsPage b={b} />}
      {route.page === 'event' && <EventDetailPage b={b} id={route.id} />}
      {route.page === 'calendar' && <CalendarPage b={b} />}
      {route.page === 'markets' && <MarketsPage b={b} />}
      {route.page === 'economy' && <EconomyPage b={b} />}
      {route.page === 'briefings' && <BriefingsPage b={b} />}
      {route.page === 'about' && <AboutPage b={b} />}
    </Layout>
  )
}
