import {
  Circle,
  Star,
  Sparkles,
  Gem,
  Diamond,
  HelpCircle,
  type LucideIcon,
} from 'lucide-react'

// ── Types ─────────────────────────────────────────────────────────────────────

export type RarityLevel =
  | 'accessible'
  | 'limited'
  | 'rare'
  | 'super-rare'
  | 'ultra-rare'
  | 'unknown'

export type RarityBadgeMode = 'light' | 'glassy'
export type RarityBadgeSize = 'sm' | 'md' | 'lg'

// ── Config ────────────────────────────────────────────────────────────────────
// Sourced from preview/components-rarity-badges.html (the authoritative design
// system reference — NOT the slightly tighter values used inside MangaCard.jsx).
// Light-mode colors and on-card "glassy" brighter variants both come from the
// "Rarity Scale — Token Reference" table at the bottom of that preview.

type RarityConfig = {
  label: string
  fg: string          // light mode foreground
  bg: string          // light mode background
  border: string      // light mode border
  fgGlassy: string    // brighter foreground for use over the dark glassy bg
  Icon: LucideIcon
  tooltip: string
  dashed?: boolean    // Unknown uses a dashed border in both modes
}

const RARITY_CONFIG: Record<RarityLevel, RarityConfig> = {
  accessible: {
    label: 'Accessible',
    fg: '#64748B',
    bg: '#F1F5F9',
    border: '#CBD5E1',
    fgGlassy: '#9CA3AF',
    Icon: Circle,
    tooltip: 'Widely available, easy to find',
  },
  limited: {
    label: 'Limited',
    fg: '#1A8A5A',
    bg: '#EDFAF3',
    border: '#A6DFCA',
    fgGlassy: '#4DC99A',
    Icon: Star,
    tooltip: 'Print run limited, harder to restock',
  },
  rare: {
    label: 'Rare',
    fg: '#2D52CC',
    bg: '#EEF2FF',
    border: '#C7D2FE',
    fgGlassy: '#8BA8F8',
    Icon: Sparkles,
    tooltip: 'Out of print or regional exclusive',
  },
  'super-rare': {
    label: 'Super Rare',
    fg: '#7C3AED',
    bg: '#F5F3FF',
    border: '#DDD6FE',
    fgGlassy: '#C4A8FF',
    Icon: Gem,
    tooltip: 'Convention or event exclusive',
  },
  'ultra-rare': {
    label: 'Ultra Rare',
    fg: '#9E6C00',
    bg: '#FFFBEB',
    border: '#FDE68A',
    fgGlassy: '#FDE68A',
    Icon: Diamond,
    tooltip: 'Lottery or extremely low availability',
  },
  unknown: {
    label: 'Unknown',
    fg: '#9CA3AF',
    bg: '#F9FAFB',
    border: '#E5E7EB',
    fgGlassy: 'rgba(255,255,255,0.4)',
    Icon: HelpCircle,
    tooltip: 'Rarity not yet determined',
    dashed: true,
  },
}

// ── Score → Rarity ────────────────────────────────────────────────────────────

export function scoreToRarity(score: number | null | undefined): RarityLevel {
  if (score == null) return 'unknown'
  if (score >= 86) return 'ultra-rare'
  if (score >= 66) return 'super-rare'
  if (score >= 41) return 'rare'
  if (score >= 21) return 'limited'
  return 'accessible'
}

// ── Size table (from preview/components-rarity-badges.html) ───────────────────
// Rounded rectangle, Space Grotesk weight 600. NOT a pill.

type SizeSpec = {
  padding: string
  fontSize: number
  radius: number
  gap: number
  iconSize: number
  iconStroke: number
}

const SIZE: Record<RarityBadgeSize, SizeSpec> = {
  sm: { padding: '3px 7px',  fontSize: 10, radius: 4, gap: 4, iconSize: 10, iconStroke: 2.5 },
  md: { padding: '5px 10px', fontSize: 12, radius: 6, gap: 6, iconSize: 13, iconStroke: 2   },
  lg: { padding: '7px 14px', fontSize: 13, radius: 8, gap: 7, iconSize: 15, iconStroke: 2   },
}

// ── Component ─────────────────────────────────────────────────────────────────

type RarityBadgeProps =
  | { score: number | null | undefined; level?: never; mode?: RarityBadgeMode; size?: RarityBadgeSize; className?: string }
  | { level: RarityLevel; score?: never; mode?: RarityBadgeMode; size?: RarityBadgeSize; className?: string }

export function RarityBadge({
  score,
  level,
  mode = 'light',
  size = 'md',
  className,
}: RarityBadgeProps) {
  const rarity = level ?? scoreToRarity(score)
  const cfg = RARITY_CONFIG[rarity]
  const sz = SIZE[size]

  const borderStyle = cfg.dashed ? 'dashed' : 'solid'

  const colorStyle =
    mode === 'glassy'
      ? {
          background: 'rgba(20,17,14,0.82)',
          backdropFilter: 'blur(6px)',
          WebkitBackdropFilter: 'blur(6px)',
          borderColor: cfg.dashed ? 'rgba(255,255,255,0.08)' : 'rgba(255,255,255,0.12)',
          color: cfg.fgGlassy,
        }
      : {
          background: cfg.bg,
          borderColor: cfg.border,
          color: cfg.fg,
        }

  return (
    <span
      title={cfg.tooltip}
      className={className}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: sz.gap,
        padding: sz.padding,
        borderRadius: sz.radius,
        fontSize: sz.fontSize,
        fontFamily: 'var(--font-display)',
        fontWeight: 600,
        lineHeight: 1,
        whiteSpace: 'nowrap',
        border: `1px ${borderStyle}`,
        ...colorStyle,
      }}
    >
      <cfg.Icon
        size={sz.iconSize}
        strokeWidth={sz.iconStroke}
        style={{ flexShrink: 0 }}
        aria-hidden="true"
      />
      {cfg.label}
    </span>
  )
}

export default RarityBadge
