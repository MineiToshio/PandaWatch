'use client'

import { SlidersHorizontal } from 'lucide-react'
import type { SortKey } from '@/lib/types'
import { useCatalogParams } from '@/lib/useCatalogParams'

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: 'date_desc',   label: 'Más reciente' },
  { value: 'date_asc',    label: 'Más antiguo' },
  { value: 'title_asc',   label: 'Título A–Z' },
  { value: 'title_desc',  label: 'Título Z–A' },
]

type SortBarProps = {
  sort: SortKey
  page: number
  pages: number
  totalTomos: number
  totalEditions: number
  totalObras: number
  onOpenFilters: () => void
}

export function SortBar({ sort, page, pages, totalTomos, totalEditions, totalObras, onOpenFilters }: SortBarProps) {
  const { isPending, set } = useCatalogParams()

  function handleSort(value: string) {
    set('sort', value)
  }

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '10px 16px',
        borderBottom: '1px solid var(--color-border)',
        background: 'var(--color-surface)',
        gap: 12,
        flexShrink: 0,
        opacity: isPending ? 0.6 : 1,
        transition: 'opacity 120ms',
      }}
    >
      {/* Stats: tomos · ediciones · obras · pág */}
      <div style={{ display: 'flex', alignItems: 'baseline', flexWrap: 'wrap', gap: 0 }}>
        <Stat value={totalTomos} label="tomos" />
        <Sep />
        <Stat value={totalEditions} label="ediciones" />
        <Sep />
        <Stat value={totalObras} label="obras" />
        {pages > 1 && (
          <>
            <Sep />
            <span style={{ fontSize: 12, color: 'var(--color-text-tertiary)', whiteSpace: 'nowrap' }}>
              pág. {page}/{pages}
            </span>
          </>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        {/* Sort select */}
        <select
          value={sort}
          onChange={e => handleSort(e.target.value)}
          style={{
            fontSize: 13,
            padding: '5px 8px',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--color-border)',
            background: 'var(--color-surface)',
            color: 'var(--color-text-primary)',
            cursor: 'pointer',
            outline: 'none',
          }}
          aria-label="Ordenar por"
        >
          {SORT_OPTIONS.map(o => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>

        {/* Mobile filter button */}
        <button
          onClick={onOpenFilters}
          aria-label="Abrir filtros"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '5px 12px',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--color-border)',
            background: 'var(--color-surface)',
            color: 'var(--color-text-primary)',
            fontSize: 13,
            cursor: 'pointer',
            fontFamily: 'var(--font-body)',
          }}
          className="sort-filter-btn"
        >
          <SlidersHorizontal size={14} />
          Filtros
        </button>
      </div>

    </div>
  )
}

function Stat({ value, label }: { value: number; label: string }) {
  return (
    <span style={{ whiteSpace: 'nowrap' }}>
      <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-primary)' }}>
        {value.toLocaleString('es')}
      </span>
      <span style={{ fontSize: 12, color: 'var(--color-text-tertiary)', marginLeft: 3 }}>
        {label}
      </span>
    </span>
  )
}

function Sep() {
  return (
    <span style={{ fontSize: 12, color: 'var(--color-text-tertiary)', margin: '0 6px' }}>·</span>
  )
}

export default SortBar
