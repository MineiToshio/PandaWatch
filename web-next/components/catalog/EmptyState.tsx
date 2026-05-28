import { SearchX } from 'lucide-react'
import Link from 'next/link'

export function EmptyState() {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '80px 24px',
        textAlign: 'center',
        color: 'var(--color-text-secondary)',
        gap: 16,
      }}
    >
      <SearchX size={48} strokeWidth={1.5} style={{ color: 'var(--ink-300)' }} />
      <div>
        <p
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 18,
            fontWeight: 600,
            color: 'var(--color-text-primary)',
            marginBottom: 6,
          }}
        >
          Sin resultados
        </p>
        <p style={{ fontSize: 14, color: 'var(--color-text-secondary)', marginBottom: 20 }}>
          No hay ediciones que coincidan con los filtros aplicados.
        </p>
        <Link
          href="/"
          style={{
            display: 'inline-block',
            padding: '8px 18px',
            borderRadius: 'var(--radius-sm)',
            background: 'var(--color-primary)',
            color: '#fff',
            fontSize: 14,
            fontWeight: 500,
            textDecoration: 'none',
          }}
        >
          Limpiar filtros
        </Link>
      </div>
    </div>
  )
}

export default EmptyState
