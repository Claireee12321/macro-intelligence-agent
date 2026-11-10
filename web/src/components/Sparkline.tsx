import { useId, useMemo, useRef, useState } from 'react'

import { fmtNum } from '../lib/format'

interface Props {
  points: [string, number][]
  label: string
  format: (v: number) => string
  width?: number
  height?: number
}

/**
 * Single-series sparkline: 2px line in the de-emphasis ink, latest point as an accent end-dot with a
 * 2px surface ring; crosshair + readout on hover and keyboard (←/→). An aria-label summarises the
 * series so the value is never hover-gated.
 */
export function Sparkline({ points, label, format, width = 112, height = 30 }: Props) {
  const [idx, setIdx] = useState<number | null>(null)
  const ref = useRef<SVGSVGElement>(null)
  const tipId = useId()
  const pad = 4
  const geo = useMemo(() => {
    if (points.length < 2) return null
    const vals = points.map((p) => p[1])
    const min = Math.min(...vals)
    const max = Math.max(...vals)
    const span = max - min || 1
    const x = (i: number) => pad + (i / (points.length - 1)) * (width - 2 * pad)
    const y = (v: number) => pad + (1 - (v - min) / span) * (height - 2 * pad)
    const d = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p[1]).toFixed(1)}`).join('')
    return { min, max, x, y, d }
  }, [points, width, height])

  if (!geo) return <span className="inline-block text-[11px] text-muted" style={{ width }}>—</span>

  const last = points.length - 1
  const summary = `${label}: ${points.length} observations from ${points[0][0]} (${format(points[0][1])}) to ${points[last][0]} (${format(points[last][1])}); range ${format(geo.min)} to ${format(geo.max)}`
  const active = idx ?? null

  const onMove = (clientX: number) => {
    const r = ref.current?.getBoundingClientRect()
    if (!r) return
    const frac = (clientX - r.left - pad) / (r.width - 2 * pad)
    setIdx(Math.max(0, Math.min(last, Math.round(frac * last))))
  }

  return (
    <span className="relative inline-block align-middle">
      <svg
        ref={ref}
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={summary}
        aria-describedby={active !== null ? tipId : undefined}
        tabIndex={0}
        className="block cursor-crosshair overflow-visible"
        onPointerMove={(e) => onMove(e.clientX)}
        onPointerLeave={() => setIdx(null)}
        onFocus={() => setIdx(last)}
        onBlur={() => setIdx(null)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowLeft') setIdx((i) => Math.max(0, (i ?? last) - 1))
          if (e.key === 'ArrowRight') setIdx((i) => Math.min(last, (i ?? last) + 1))
        }}
      >
        <path d={geo.d} fill="none" stroke="var(--muted)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        {active !== null && (
          <line x1={geo.x(active)} x2={geo.x(active)} y1={1} y2={height - 1} stroke="var(--axis)" strokeWidth={1} />
        )}
        <circle cx={geo.x(active ?? last)} cy={geo.y(points[active ?? last][1])} r={4} fill="var(--s1)" stroke="var(--surface)" strokeWidth={2} />
      </svg>
      {active !== null && (
        <span
          id={tipId}
          role="status"
          className="pointer-events-none absolute bottom-full left-1/2 z-20 mb-1 -translate-x-1/2 whitespace-nowrap rounded-md border border-line bg-surface px-2 py-1 text-[11px] shadow-sm"
        >
          <span className="font-semibold text-ink">{format(points[active][1])}</span>{' '}
          <span className="text-ink-2">{points[active][0]}</span>
        </span>
      )}
    </span>
  )
}

export const plainFormat = (decimals: number) => (v: number) => fmtNum(v, decimals)
