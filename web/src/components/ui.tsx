import type { ReactNode } from 'react'

import { importanceLabel, REGION_NAMES } from '../lib/format'

export function Card({ title, aside, children, className = '' }: { title?: ReactNode; aside?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`min-w-0 rounded-xl border border-line bg-surface p-4 sm:p-5 ${className}`}>
      {(title || aside) && (
        <header className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          {title && <h2 className="text-[15px] font-semibold text-ink">{title}</h2>}
          {aside && <div className="text-xs text-muted">{aside}</div>}
        </header>
      )}
      {children}
    </section>
  )
}

export function SubTitle({ children, aside }: { children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="mb-2 mt-4 flex flex-wrap items-center justify-between gap-2 first:mt-0">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-2">{children}</h3>
      {aside}
    </div>
  )
}

export type Provenance = 'fact' | 'official' | 'consensus' | 'ai' | 'ai_impact' | 'observed'

const PROV: Record<Provenance, { label: string; swatch: string; title: string }> = {
  fact: { label: 'Fact', swatch: 'bg-s1', title: 'Attributed reporting from the named source' },
  official: { label: 'Official data', swatch: 'bg-s1', title: 'Official statistics (agency via FRED, Treasury, NY Fed)' },
  consensus: { label: 'Consensus', swatch: 'bg-muted', title: 'Published forecast, with its source named — never inferred' },
  ai: { label: 'AI interpretation', swatch: 'bg-s2', title: 'Model-generated interpretation — not a fact' },
  ai_impact: { label: 'AI potential impact', swatch: 'bg-s2', title: 'Model-generated potential market impact — not a forecast' },
  observed: { label: 'Observed market data', swatch: 'bg-s3', title: 'Measured market moves with stated window and source' },
}

export function ProvenanceBadge({ kind }: { kind: Provenance }) {
  const p = PROV[kind]
  return (
    <span title={p.title} className="inline-flex items-center gap-1.5 rounded-full border border-line px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-ink-2">
      <span aria-hidden className={`inline-block h-2 w-2 rounded-full ${p.swatch}`} />
      {p.label}
    </span>
  )
}

export function StaleBadge({ stale, reason }: { stale: boolean; reason?: string }) {
  if (!stale) return null
  return (
    <span title={reason || 'Older than its expected update interval'} className="inline-flex items-center gap-1 rounded-full border border-line px-1.5 py-0.5 text-[11px] text-ink-2">
      <span aria-hidden className="text-warning">⚠</span> Stale
    </span>
  )
}

export function FreshDot({ ok }: { ok: boolean }) {
  return ok ? (
    <span className="inline-flex items-center gap-1 text-ink-2"><span aria-hidden className="text-good">●</span>OK</span>
  ) : (
    <span className="inline-flex items-center gap-1 text-ink-2"><span aria-hidden className="text-critical">✕</span>Failed</span>
  )
}

/** Importance 0–100 as a thin meter (accent fill on a lighter step of the same ramp) + label. */
export function Importance({ value, reasons }: { value: number; reasons?: string[] }) {
  const pct = Math.max(0, Math.min(100, value))
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] text-ink-2" title={reasons?.join('\n') ?? `Importance ${value}`}>
      <span aria-hidden className="relative inline-block h-1 w-10 overflow-hidden rounded-full bg-s1-track">
        <span className="absolute inset-y-0 left-0 rounded-full bg-s1" style={{ width: `${pct}%` }} />
      </span>
      {importanceLabel(value)} <span className="tabular text-muted">{Math.round(value)}</span>
    </span>
  )
}

export function RegionTag({ region }: { region: string }) {
  return (
    <span title={REGION_NAMES[region] ?? region} className="rounded border border-line px-1.5 py-px text-[11px] font-medium text-ink-2">
      {region}
    </span>
  )
}

export function Ext({ href, children, className = '' }: { href: string; children: ReactNode; className?: string }) {
  if (!href) return <span className={className}>{children}</span>
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className={`underline decoration-line underline-offset-2 hover:decoration-ink-2 ${className}`}>
      {children}
    </a>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="text-sm text-muted">{children}</p>
}

export function Disabled({ what }: { what: string }) {
  return (
    <p className="rounded-lg bg-wash px-3 py-2 text-sm text-ink-2">
      {what} is not available: AI analysis is turned off (data-only mode). Facts, official data, consensus and
      observed market moves below are unaffected.
    </p>
  )
}
