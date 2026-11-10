import { useEffect, useState } from 'react'

export type Route =
  | { page: 'overview' }
  | { page: 'events' }
  | { page: 'event'; id: string }
  | { page: 'calendar' }
  | { page: 'markets' }
  | { page: 'economy' }
  | { page: 'briefings' }
  | { page: 'about' }

export function parseHash(hash: string): Route {
  const parts = hash.replace(/^#\/?/, '').split('/').filter(Boolean).map(decodeURIComponent)
  switch (parts[0]) {
    case 'events':
      return parts[1] ? { page: 'event', id: parts[1] } : { page: 'events' }
    case 'calendar':
    case 'markets':
    case 'economy':
    case 'briefings':
    case 'about':
      return { page: parts[0] }
    default:
      return { page: 'overview' }
  }
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash))
  useEffect(() => {
    const onChange = () => {
      setRoute(parseHash(window.location.hash))
      window.scrollTo({ top: 0 })
    }
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return route
}

export const eventHref = (id: string) => `#/events/${encodeURIComponent(id)}`
