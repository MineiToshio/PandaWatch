import type { CSSProperties } from 'react'
import { signalChipMeta } from '@/lib/vocab'

// Spec source: preview/components-edition-badges.html → "Signal Chips — Why It Was Detected"
// Pill shape (radius 999), tight padding, small icon. NOT the rectangular filter-chip
// shape from `core/Chip.tsx`. Keeps the visual distinction the bundle established.
// Vocabulario (icon/label/bg/fg) en lib/vocab.ts — fuente única (auditoría #12).

type SignalChipSize = 'sm' | 'md'

const SIZE: Record<SignalChipSize, CSSProperties> = {
  md: { padding: '3px 8px', fontSize: 11, gap: 4 },
  sm: { padding: '2px 7px', fontSize: 10, gap: 3 },
}

const ICON_SIZE: Record<SignalChipSize, number> = { md: 10, sm: 9 }

type SignalChipProps = {
  signal: string
  size?: SignalChipSize
  className?: string
}

export function SignalChip({ signal, size = 'md', className }: SignalChipProps) {
  const meta = signalChipMeta(signal)
  if (!meta) return null
  const sz = SIZE[size]

  return (
    <span
      className={className}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        borderRadius: 999,
        fontWeight: 500,
        fontFamily: 'var(--font-body)',
        whiteSpace: 'nowrap',
        background: meta.bg,
        color: meta.fg,
        ...sz,
      }}
    >
      <meta.icon
        size={ICON_SIZE[size]}
        strokeWidth={2.5}
        style={{ flexShrink: 0 }}
        aria-hidden="true"
      />
      {meta.label}
    </span>
  )
}

export default SignalChip
