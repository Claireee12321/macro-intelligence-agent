import { useEffect, useState } from 'react'

import type { Bundle } from '../types'

const FILES: Record<keyof Bundle, string> = {
  meta: 'meta.json',
  overview: 'overview.json',
  events: 'events.json',
  calendar: 'calendar.json',
  markets: 'markets.json',
  economy: 'economy.json',
  briefings: 'briefings.json',
  sources: 'sources.json',
}

async function loadBundle(): Promise<Bundle> {
  const base = `${import.meta.env.BASE_URL}data/`
  const entries = await Promise.all(
    (Object.keys(FILES) as (keyof Bundle)[]).map(async (k) => {
      const res = await fetch(base + FILES[k], { cache: 'no-store' })
      if (!res.ok) throw new Error(`${FILES[k]}: HTTP ${res.status}`)
      return [k, await res.json()] as const
    }),
  )
  return Object.fromEntries(entries) as unknown as Bundle
}

export type LoadState = { status: 'loading' } | { status: 'error'; error: string } | { status: 'ready'; data: Bundle }

export function useBundle(): LoadState {
  const [state, setState] = useState<LoadState>({ status: 'loading' })
  useEffect(() => {
    let alive = true
    loadBundle()
      .then((data) => alive && setState({ status: 'ready', data }))
      .catch((e: unknown) => alive && setState({ status: 'error', error: e instanceof Error ? e.message : String(e) }))
    return () => {
      alive = false
    }
  }, [])
  return state
}
