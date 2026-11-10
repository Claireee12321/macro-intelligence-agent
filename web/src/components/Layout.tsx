import { useEffect, useState, type ReactNode } from 'react'

import { ago, fmtET, hoursSince } from '../lib/format'
import type { Route } from '../lib/router'
import type { Meta } from '../types'

const NAV: { page: Route['page']; label: string; href: string }[] = [
  { page: 'overview', label: 'Overview', href: '#/' },
  { page: 'events', label: 'Events', href: '#/events' },
  { page: 'calendar', label: 'Calendar', href: '#/calendar' },
  { page: 'markets', label: 'Markets', href: '#/markets' },
  { page: 'economy', label: 'Economy', href: '#/economy' },
  { page: 'briefings', label: 'Briefings', href: '#/briefings' },
  { page: 'about', label: 'About', href: '#/about' },
]

function ThemeToggle() {
  const [theme, setTheme] = useState<string>(() => localStorage.getItem('theme') ?? 'auto')
  useEffect(() => {
    const el = document.documentElement
    if (theme === 'auto') el.removeAttribute('data-theme')
    else el.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }, [theme])
  const next = theme === 'auto' ? 'light' : theme === 'light' ? 'dark' : 'auto'
  return (
    <button type="button" onClick={() => setTheme(next)} className="rounded-md border border-line px-2 py-1 text-xs text-ink-2 hover:bg-wash" title="Theme: auto → light → dark">
      Theme: {theme}
    </button>
  )
}

export function Layout({ meta, route, children }: { meta: Meta; route: Route; children: ReactNode }) {
  const age = hoursSince(meta.generated_at) ?? 0
  const stale = !meta.is_sample && age > meta.stale_site_after_hours
  const active = route.page === 'event' ? 'events' : route.page
  return (
    <div className="min-h-screen overflow-x-clip">
      {meta.is_sample && (
        <div role="alert" className="bg-ink px-4 py-2 text-center text-sm font-semibold text-surface">
          SAMPLE DATA — a fictional, synthetic day showing what the agent produces. Not real news, data or analysis.
        </div>
      )}
      <header className="sticky top-0 z-30 border-b border-line bg-page/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2 px-4 pt-3">
          <a href="#/" className="text-[15px] font-semibold tracking-tight text-ink">Macro Intelligence</a>
          <div className="flex items-center gap-2 text-xs text-ink-2">
            {meta.is_sample ? (
              <span className="inline-flex items-center gap-1">Sample data · generated {fmtET(meta.generated_at)}</span>
            ) : (
              <span title={`Generated ${fmtET(meta.generated_at)}\n${meta.schedule}`} className="inline-flex items-center gap-1">
                <span aria-hidden className={stale ? 'text-warning' : 'text-good'}>{stale ? '⚠' : '●'}</span>
                Updated {ago(meta.generated_at)}
              </span>
            )}
            <span className="hidden rounded-full border border-line px-2 py-0.5 sm:inline">{meta.mode === 'ai' ? 'AI analysis on' : meta.mode === 'sample' ? 'Sample' : 'Data-only'}</span>
            <ThemeToggle />
          </div>
        </div>
        <nav className="mx-auto max-w-6xl overflow-x-auto px-2" aria-label="Sections">
          <ul className="flex gap-1 whitespace-nowrap py-2">
            {NAV.map((n) => (
              <li key={n.page}>
                <a
                  href={n.href}
                  aria-current={active === n.page ? 'page' : undefined}
                  className={`block rounded-md px-2.5 py-1.5 text-sm ${active === n.page ? 'bg-wash font-semibold text-ink' : 'text-ink-2 hover:bg-wash'}`}
                >
                  {n.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      </header>
      {stale && (
        <div role="alert" className="mx-auto mt-3 max-w-6xl px-4">
          <div className="rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink">
            <span aria-hidden className="mr-1 text-warning">⚠</span>
            <strong>Data is {Math.round(age)} hours old.</strong> The scheduled update may have failed; treat everything below as stale.
          </div>
        </div>
      )}
      <main className="mx-auto min-w-0 max-w-6xl px-4 py-4 sm:py-6">{children}</main>
      <footer className="mx-auto max-w-6xl px-4 pb-8 text-[11px] leading-relaxed text-muted">
        Personal research tool, not investment advice. Facts are attributed to their sources; consensus is shown only when a
        published forecast exists; AI content (when enabled) is labeled and is interpretation, not fact. Market quotes may be delayed.
        Generated {fmtET(meta.generated_at)} · v{meta.version}
      </footer>
    </div>
  )
}
