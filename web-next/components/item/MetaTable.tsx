import { formatDate, PRODUCT_TYPE_LABELS } from '@/lib/format'
import { RARITY_META, type RarityValue } from '@/components/modules/RarityBadge'
import type { Item } from '@/lib/types'

type Row = {
  label: string
  value: string | number | null | undefined
}

export function MetaTable({ item }: { item: Item }) {
  const rows: Row[] = [
    { label: 'ISBN',          value: item.isbn },
    { label: 'Lanzamiento',   value: item.release_date && formatDate(item.release_date) },
    { label: 'Autor',         value: item.author },
    { label: 'Editorial',     value: item.publisher },
    { label: 'País',          value: item.country },
    { label: 'Idioma',        value: item.language },
    { label: 'Tipo',          value: item.product_type && (PRODUCT_TYPE_LABELS[item.product_type] ?? item.product_type) },
    { label: 'Rareza',        value: item.rarity ? (RARITY_META[item.rarity as RarityValue]?.label ?? item.rarity) : undefined },
    { label: 'Detectado',     value: item.detected_at && formatDate(item.detected_at) },
    {
      label: 'Estandarizado',
      value: item.standardized_at ? formatDate(item.standardized_at) : 'Pendiente',
    },
  ].filter(r => r.value !== undefined && r.value !== null && r.value !== '')

  return (
    <section>
      <h2 style={{
        fontSize: 11, fontWeight: 600, textTransform: 'uppercase',
        letterSpacing: '0.08em', color: 'var(--color-text-secondary)',
        marginBottom: 12, marginTop: 0,
      }}>
        Datos del producto
      </h2>
      <dl style={{ margin: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
        {rows.map(({ label, value }) => (
          <div key={label} style={{ display: 'flex', gap: 8 }}>
            <dt style={{
              fontSize: 12, color: 'var(--color-text-tertiary)',
              width: 112, flexShrink: 0,
            }}>
              {label}
            </dt>
            <dd style={{ fontSize: 13, color: 'var(--color-text-primary)', margin: 0 }}>
              {String(value)}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  )
}

export default MetaTable
