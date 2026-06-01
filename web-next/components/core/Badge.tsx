import type { CSSProperties, ReactNode } from 'react'
import { cn } from '@/lib/styles'

type BadgeVariant = 'green' | 'yellow' | 'orange' | 'red' | 'neutral'

export type BadgeProps = {
  children?: ReactNode
  variant?: BadgeVariant
  className?: string
}

// Hex values aligned with the PandaWatch design system tokens
const variantStyles: Record<BadgeVariant, CSSProperties> = {
  green: {
    // Bamboo / Limited–Rare green
    background: '#EDFAF3',
    border: '1px solid #A6DFCA',
    color: '#1A8A5A',
  },
  yellow: {
    // Amber / Ultra-Rare
    background: '#FFFBEB',
    border: '1px solid #FDE68A',
    color: '#9E6C00',
  },
  orange: {
    // Vermillion / Secondary — warm orange-red
    background: '#FEF3EF',
    border: '1px solid #FABEAD',
    color: '#D93D1A',
  },
  red: {
    // Deeper vermillion
    background: '#FEF3EF',
    border: '1px solid #F69279',
    color: '#B53215',
  },
  neutral: {
    background: 'var(--ink-100)',
    border: '1px solid var(--ink-200)',
    color: 'var(--ink-500)',
  },
}

export function Badge({ children, variant, className }: BadgeProps) {
  const resolvedVariant = variant ?? 'neutral'
  const label = children

  return (
    <span
      className={cn(
        'inline-flex items-center justify-center whitespace-nowrap font-semibold',
        className,
      )}
      style={{
        ...variantStyles[resolvedVariant],
        padding: '4px 9px',
        borderRadius: 6,
        fontSize: 12,
        fontFamily: 'var(--font-display)',
      }}
    >
      {label}
    </span>
  )
}

export default Badge
