'use client'

import { useRouter, useSearchParams, usePathname } from 'next/navigation'
import { SlidersHorizontal } from 'lucide-react'
import type { SortKey } from '@/lib/types'

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: 'score_desc',  label: 'Puntuación ↓' },
  { value: 'score_asc',   label: 'Puntuación ↑' },
  { value: 'date_desc',   label: 'Más reciente' },
  { value: 'date_asc',    label: 'Más antiguo' },
  { value: 'title_asc',   label: 'Título A–Z' },
  { value: 'title_desc',  label: 'Título Z–A' },
]

type SortBarProps = {
  total: number
  sort: SortKey
  page: number
  pages: number
  onOpenFilters: () => void
}

export function SortBar({ total, sort, page, pages, onOpenFilters }: SortBarProps) {
  const router   = useRouter()
  const pathname = usePathname()
  const params   = useSearchParams()

  function handleSort(value: string) {
    const next = new URLSearchParams(params.toString())
    next.set('sort', value)
    next.delete('page')
    router.replace(`${pathname}?${next.toString()}`)
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
      }}
    >
      {/* Count + page info */}
      <span style={{ fontSize: 13, color: 'var(--color-text-secondary)', whiteSpace: 'nowrap' }}>
        {total.toLocaleString('es')} ediciones
        {pages > 1 && (
          <span style={{ color: 'var(--color-text-tertiary)' }}>
            {' '}· pág. {page}/{pages}
          </span>
        )}
      </span>

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

export default SortBar
