import type { Quote } from '../types'

const ET = 'America/New_York'

const dtFmt = new Intl.DateTimeFormat('en-US', { timeZone: ET, month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
const dateFmt = new Intl.DateTimeFormat('en-US', { timeZone: ET, weekday: 'short', month: 'short', day: 'numeric' })
const timeFmt = new Intl.DateTimeFormat('en-US', { timeZone: ET, hour: 'numeric', minute: '2-digit' })
const ymdFmt = new Intl.DateTimeFormat('en-CA', { timeZone: ET, year: 'numeric', month: '2-digit', day: '2-digit' })

export function fmtET(iso: string | null | undefined): string {
  if (!iso) return ''
  return `${dtFmt.format(new Date(iso))} ET`
}

export function fmtTimeET(iso: string | null | undefined): string {
  if (!iso) return ''
  return `${timeFmt.format(new Date(iso))} ET`
}

/** "Thu, Nov 5" for an ISO date (YYYY-MM-DD) interpreted as a calendar day. */
export function fmtDay(ymd: string): string {
  const [y, m, d] = ymd.split('-').map(Number)
  return dateFmt.format(new Date(Date.UTC(y, m - 1, d, 17)))
}

export function etYmd(date: Date = new Date()): string {
  return ymdFmt.format(date)
}

export function hoursSince(iso: string | null | undefined): number | null {
  if (!iso) return null
  return (Date.now() - new Date(iso).getTime()) / 3_600_000
}

export function ago(iso: string | null | undefined): string {
  const h = hoursSince(iso)
  if (h === null) return 'unknown'
  if (h < 1 / 60) return 'just now'
  if (h < 1) return `${Math.round(h * 60)} min ago`
  if (h < 48) return `${Math.round(h)} h ago`
  return `${Math.round(h / 24)} days ago`
}

export function fmtNum(v: number, decimals: number): string {
  return v.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

export function fmtValue(v: number | null, units: Quote['units'], decimals: number): string {
  if (v === null || v === undefined) return 'n/a'
  if (units === '%') return `${v.toFixed(decimals)}%`
  if (units === 'bp') return `${v > 0 ? '+' : ''}${v.toFixed(0)}bp`
  return fmtNum(v, decimals)
}

export function fmtChange(c: number | null, units: Quote['change_units']): string {
  if (c === null || c === undefined) return 'n/a'
  const sign = c > 0 ? '+' : c < 0 ? '−' : '±'
  const a = Math.abs(c)
  if (units === 'bp') return `${sign}${a < 10 && a % 1 !== 0 ? a.toFixed(1) : a.toFixed(0)}bp`
  if (units === 'pts') return `${sign}${a.toFixed(2)}`
  return `${sign}${a.toFixed(2)}%`
}

export function arrow(c: number | null): string {
  if (c === null || c === undefined || c === 0) return '→'
  return c > 0 ? '▲' : '▼'
}

export const REGION_NAMES: Record<string, string> = {
  US: 'United States', EA: 'Euro area', UK: 'United Kingdom', JP: 'Japan', CN: 'China', CA: 'Canada',
  AU: 'Australia', NZ: 'New Zealand', CH: 'Switzerland', SE: 'Sweden', NO: 'Norway', Global: 'Global', Other: 'Other',
}

export const TOPIC_NAMES: Record<string, string> = {
  inflation: 'Inflation', labor: 'Labor', growth: 'Growth', monetary_policy: 'Monetary policy',
  fiscal_policy: 'Fiscal', financial_conditions: 'Financial conditions', rates: 'Rates', fx: 'FX',
  energy_commodities: 'Energy & commodities', trade_geopolitics: 'Trade & geopolitics', housing: 'Housing',
  equities: 'Equities', other: 'Other',
}

export function importanceLabel(v: number): string {
  if (v >= 80) return 'Major'
  if (v >= 65) return 'Notable'
  return 'Moderate'
}

/** Compact as-of: intraday quotes from today show the time; everything else shows the date ("Nov 4"). */
export function shortAsOf(iso: string | null | undefined, intraday = true): string {
  if (!iso) return 'n/a'
  const d = new Date(iso)
  if (intraday && etYmd(d) === etYmd()) return fmtTimeET(iso)
  return new Intl.DateTimeFormat('en-US', { timeZone: ET, month: 'short', day: 'numeric' }).format(d)
}

/** Calendar-day age in US Eastern: "today", "yesterday", "3 days ago". */
export function dayAge(iso: string | null | undefined): string {
  if (!iso) return ''
  const [a, b] = [etYmd(new Date(iso)), etYmd()]
  const days = Math.round((Date.parse(b + 'T12:00:00Z') - Date.parse(a + 'T12:00:00Z')) / 86_400_000)
  if (days <= 0) return 'today'
  if (days === 1) return 'yesterday'
  return `${days} days ago`
}

/** "Released Tue, Nov 10, 8:30 AM ET (today)" */
export function releasedLabel(iso: string | null | undefined): string {
  if (!iso) return 'Release time unknown'
  return `Released ${fmtDay(etYmd(new Date(iso)))}, ${fmtTimeET(iso)} (${dayAge(iso)})`
}
