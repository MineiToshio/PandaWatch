'use client'

import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useCatalogParams } from '@/lib/useCatalogParams'

type PaginationProps = {
  total: number
  current: number
}

function buildPageWindow(current: number, total: number): (number | '...')[] {
  if (total <= 7) {
    return Array.from({ length: total }, (_, i) => i + 1)
  }
  const window: (number | '...')[] = [1]
  const lo = Math.max(2, current - 2)
  const hi = Math.min(total - 1, current + 2)

  if (lo > 2) window.push('...')
  for (let i = lo; i <= hi; i++) window.push(i)
  if (hi < total - 1) window.push('...')
  window.push(total)
  return window
}

export function Pagination({ total, current }: PaginationProps) {
  const { isPending, set } = useCatalogParams()

  function goTo(page: number) {
    // push (no replace): cada página es una entrada de historial — "atrás"
    // desde la pág. 5 vuelve a la 4, no sale del sitio
    set('page', page === 1 ? null : String(page), { push: true })
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const pageWindow = buildPageWindow(current, total)

  const btnBase: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    minWidth: 36,
    height: 36,
    padding: '0 6px',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--color-border)',
    background: 'var(--color-surface)',
    color: 'var(--color-text-primary)',
    fontSize: 13,
    cursor: 'pointer',
    fontFamily: 'var(--font-body)',
    transition: 'background 0.12s, border-color 0.12s',
  }

  const activeBtnBase: React.CSSProperties = {
    ...btnBase,
    background: 'var(--color-primary)',
    border: '1px solid var(--color-primary)',
    color: '#fff',
    fontWeight: 600,
    cursor: 'default',
  }

  const disabledBtn: React.CSSProperties = {
    ...btnBase,
    opacity: 0.4,
    cursor: 'not-allowed',
  }

  return (
    <nav
      aria-label="Paginación"
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 6,
        padding: '24px 16px 40px',
        flexWrap: 'wrap',
        opacity: isPending ? 0.6 : 1,
        transition: 'opacity 120ms',
      }}
    >
      {/* Prev */}
      <button
        onClick={() => goTo(current - 1)}
        disabled={current === 1}
        style={current === 1 ? disabledBtn : btnBase}
        aria-label="Página anterior"
      >
        <ChevronLeft size={16} />
      </button>

      {pageWindow.map((p, i) =>
        p === '...' ? (
          <span
            key={`ellipsis-${i}`}
            style={{ fontSize: 13, color: 'var(--color-text-tertiary)', padding: '0 4px' }}
          >
            …
          </span>
        ) : (
          <button
            key={p}
            onClick={() => p !== current && goTo(p)}
            style={p === current ? activeBtnBase : btnBase}
            aria-label={`Ir a página ${p}`}
            aria-current={p === current ? 'page' : undefined}
          >
            {p}
          </button>
        )
      )}

      {/* Next */}
      <button
        onClick={() => goTo(current + 1)}
        disabled={current === total}
        style={current === total ? disabledBtn : btnBase}
        aria-label="Página siguiente"
      >
        <ChevronRight size={16} />
      </button>
    </nav>
  )
}

export default Pagination
