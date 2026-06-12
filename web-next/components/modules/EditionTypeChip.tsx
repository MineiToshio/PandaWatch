import type { CSSProperties } from 'react'
import { BadgeCheck } from 'lucide-react'
import { editionTypeLabel } from '@/lib/format'

// Chip del TIPO de edición, derivado del edition_key (autoritativo).
// Complementa los SignalChips (señales detectadas en el scrape): desde la
// política de títulos 2026-06-12 el title es el nombre OFICIAL y no lleva el
// tipo inyectado ("Kanzenban"/"Deluxe"), así que el tipo se comunica acá.
// Misma forma pill que SignalChip (preview/components-edition-badges.html).

type EditionTypeChipSize = 'sm' | 'md'

const SIZE: Record<EditionTypeChipSize, CSSProperties> = {
  md: { padding: '3px 8px', fontSize: 11, gap: 4 },
  sm: { padding: '2px 7px', fontSize: 10, gap: 3 },
}

const ICON_SIZE: Record<EditionTypeChipSize, number> = { md: 10, sm: 9 }

type EditionTypeChipProps = {
  editionKey?: string
  size?: EditionTypeChipSize
  className?: string
}

export function EditionTypeChip({ editionKey, size = 'md', className }: EditionTypeChipProps) {
  const label = editionTypeLabel(editionKey)
  if (!label) return null
  const sz = SIZE[size]

  return (
    <span
      className={className}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        borderRadius: 999,
        fontWeight: 600,
        fontFamily: 'var(--font-body)',
        whiteSpace: 'nowrap',
        background: '#F4EFFA',
        color: '#6B3FA0',
        ...sz,
      }}
    >
      <BadgeCheck
        size={ICON_SIZE[size]}
        strokeWidth={2.5}
        style={{ flexShrink: 0 }}
        aria-hidden="true"
      />
      {label}
    </span>
  )
}

export default EditionTypeChip
