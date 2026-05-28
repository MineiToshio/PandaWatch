import type { CSSProperties, ReactNode } from 'react'
import { cn } from '@/lib/styles'

export type ChipVariant = 'accent' | 'neutral' | 'info' | 'success' | 'warning' | 'destructive' | 'dark'
export type ChipSize = 'sm' | 'md'

export type ChipProps = {
  variant?: ChipVariant
  size?: ChipSize
  dismissible?: boolean
  onDismiss?: () => void
  className?: string
  children: ReactNode
}

// Color set from preview/components-filter-chips.html ("Applied Filter Chips").
// Filter chips are rounded RECTANGLES (radius 6, not pill) with semantic colors.
function variantColors(variant: ChipVariant): {
  bg: string
  border: string
  fg: string
  /** semi-transparent dismiss-button background; falls back to fg-tinted for colored chips */
  dismissBg: string
} {
  switch (variant) {
    case 'accent':
    case 'success':
      return { bg: '#EDFAF3', border: '#A6DFCA', fg: '#1A8A5A', dismissBg: 'rgba(26,138,90,0.15)' }
    case 'info':
      return { bg: '#EEF2FF', border: '#C7D2FE', fg: '#2D52CC', dismissBg: 'rgba(45,82,204,0.15)' }
    case 'warning':
      return { bg: '#FFFBEB', border: '#FDE68A', fg: '#9E6C00', dismissBg: 'rgba(158,108,0,0.15)' }
    case 'destructive':
      return { bg: '#FEF3EF', border: '#FABEAD', fg: '#D93D1A', dismissBg: 'rgba(217,61,26,0.15)' }
    case 'dark':
      // Dark "applied filter" chip (e.g. Country / Publisher in the bundle preview)
      return { bg: '#1C1915', border: 'transparent',     fg: '#FFFFFF', dismissBg: 'rgba(255,255,255,0.18)' }
    case 'neutral':
    default:
      return { bg: 'var(--ink-100)', border: 'var(--ink-200)', fg: 'var(--ink-600)', dismissBg: 'rgba(0,0,0,0.08)' }
  }
}

// Size table from preview/components-filter-chips.html
const SIZE_STYLE: Record<ChipSize, CSSProperties> = {
  md: { padding: '5px 10px', fontSize: 12, borderRadius: 6, gap: 5 },
  sm: { padding: '3px 8px',  fontSize: 11, borderRadius: 5, gap: 4 },
}

export function Chip({
  variant = 'neutral',
  size = 'md',
  dismissible,
  onDismiss,
  className,
  children,
}: ChipProps) {
  const c = variantColors(variant)
  const sz = SIZE_STYLE[size]

  return (
    <span
      className={cn('inline-flex items-center whitespace-nowrap font-medium', className)}
      style={{
        background: c.bg,
        color: c.fg,
        border: `1px solid ${c.border}`,
        ...sz,
        fontFamily: 'var(--font-body)',
      }}
    >
      {children}
      {(dismissible || onDismiss) && (
        <button
          type="button"
          aria-label="Dismiss"
          onClick={onDismiss}
          className="ml-1 inline-flex items-center justify-center"
          style={{
            width: 14,
            height: 14,
            borderRadius: 3,
            background: c.dismissBg,
            color: 'inherit',
            border: 'none',
            padding: 0,
            cursor: 'pointer',
            flexShrink: 0,
          }}
        >
          <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" aria-hidden="true">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      )}
    </span>
  )
}

export default Chip
