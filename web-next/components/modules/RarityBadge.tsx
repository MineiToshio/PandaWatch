import type { CSSProperties, ReactNode } from 'react'

// Fuente ÚNICA de labels/colores/íconos de rareza. Antes vivía copiada en
// EditionCard, ItemHero, SidebarFilters y MetaTable — cambiar un color exigía
// tocar 4 archivos.
export const RARITY_VALUES = ['common', 'rare', 'super_rare', 'ultra_rare'] as const
export type RarityValue = (typeof RARITY_VALUES)[number]

export const RARITY_META: Record<
  RarityValue,
  { label: string; color: string; icon: ReactNode }
> = {
  common: {
    label: 'Accessible',
    color: '#9CA3AF',
    icon: (
      <svg width={9} height={9} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
        <circle cx={12} cy={12} r={10} />
      </svg>
    ),
  },
  rare: {
    label: 'Rare',
    color: '#8BA8F8',
    icon: (
      <svg width={9} height={9} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
      </svg>
    ),
  },
  super_rare: {
    label: 'Super Rare',
    color: '#C4A8FF',
    icon: (
      <svg width={9} height={9} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <path d="M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5z" />
      </svg>
    ),
  },
  ultra_rare: {
    label: 'Ultra Rare',
    color: '#FDE68A',
    icon: (
      <svg width={9} height={9} viewBox="0 0 24 24" fill="currentColor">
        <path d="M6 3h12l4 6-10 13L2 9z" />
      </svg>
    ),
  },
}

/** Pill oscuro de rareza. `style` permite posicionarlo (absolute en cards). */
export function RarityBadge({ rarity, style }: { rarity: string; style?: CSSProperties }) {
  const meta = RARITY_META[rarity as RarityValue]
  if (!meta) return null
  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        padding: '4px 8px',
        borderRadius: 5,
        fontSize: 10,
        fontWeight: 600,
        fontFamily: 'var(--font-display)',
        color: meta.color,
        background: 'rgba(20,17,14,0.82)',
        backdropFilter: 'blur(6px)',
        border: '1px solid rgba(255,255,255,0.12)',
        ...style,
      }}
    >
      {meta.icon}
      {meta.label}
    </div>
  )
}

export default RarityBadge
