import type { CSSProperties } from 'react'
import {
  Star,
  Sparkles,
  Package,
  Layers,
  BookOpen,
  Gem,
  Globe,
  Trophy,
  type LucideIcon,
} from 'lucide-react'

// Spec source: preview/components-edition-badges.html → "Signal Chips — Why It Was Detected"
// Pill shape (radius 999), tight padding, small icon. NOT the rectangular filter-chip
// shape from `core/Chip.tsx`. Keeps the visual distinction the bundle established.

type SignalMeta = {
  IconComponent: LucideIcon
  label: string
  /** Light tint + fg pair from the bundle's signal-chip examples (or neutral default). */
  bg: string
  fg: string
}

const NEUTRAL: Pick<SignalMeta, 'bg' | 'fg'> = { bg: '#EDE9E2', fg: '#706560' }

const SIGNAL_META: Record<string, SignalMeta> = {
  limited:            { IconComponent: Star,      label: 'Limited Edition',  bg: '#FEF3EF', fg: '#D93D1A' },
  special_edition:    { IconComponent: Sparkles,  label: 'Special Edition',  bg: '#EDFAF3', fg: '#1A8A5A' },
  collector:          { IconComponent: Trophy,    label: 'Collector',        bg: '#EDFAF3', fg: '#1A8A5A' },
  box_set:            { IconComponent: Package,   label: 'Box Set',          bg: '#EEF2FF', fg: '#2D52CC' },
  variant_cover:      { IconComponent: Layers,    label: 'Variant Cover',    bg: '#FFFBEB', fg: '#9E6C00' },
  artbook:            { IconComponent: BookOpen,  label: 'Artbook',          bg: '#EEF2FF', fg: '#2D52CC' },
  deluxe:             { IconComponent: Gem,       label: 'Deluxe',           bg: '#EEF2FF', fg: '#2D52CC' },
  hardcover:          { IconComponent: BookOpen,  label: 'Hardcover',        ...NEUTRAL },
  kanzenban:          { IconComponent: Layers,    label: 'Kanzenban',        bg: '#EEF2FF', fg: '#2D52CC' },
  lore_edition:       { IconComponent: Sparkles,  label: 'Special Edition',  bg: '#EDFAF3', fg: '#1A8A5A' },
  omnibus:            { IconComponent: BookOpen,  label: 'Omnibus',          ...NEUTRAL },
  bonus:              { IconComponent: Package,   label: 'With Extra',       bg: '#EDFAF3', fg: '#1A8A5A' },
  retailer_exclusive: { IconComponent: Globe,     label: 'Store Exclusive',  bg: '#FFFBEB', fg: '#9E6C00' },
}

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
  const meta = SIGNAL_META[signal]
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
      <meta.IconComponent
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
