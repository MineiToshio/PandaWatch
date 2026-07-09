'use client'

import Link from 'next/link'
import { useEffect } from 'react'
import { TriangleAlert } from 'lucide-react'

// Antes: sin error.tsx, un throw de readRawItems() (o cualquier otro error de
// render) mostraba la pantalla genérica de Next, en inglés (auditoría #7).
// error.tsx boundary tiene que ser Client Component (requisito de Next).
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    console.error(error)
  }, [error])

  return (
    <main
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: 'calc(100vh - var(--header-height))',
        padding: '80px 24px',
        textAlign: 'center',
        gap: 16,
      }}
    >
      <TriangleAlert size={48} strokeWidth={1.5} style={{ color: 'var(--color-secondary)' }} />
      <div>
        <h1
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 22,
            fontWeight: 700,
            color: 'var(--color-text-primary)',
            marginBottom: 8,
          }}
        >
          Algo salió mal
        </h1>
        <p style={{ fontSize: 14, color: 'var(--color-text-secondary)', maxWidth: 420, marginBottom: 20 }}>
          Hubo un error inesperado cargando esta página. Podés reintentar o
          volver al catálogo.
        </p>
        <div style={{ display: 'flex', gap: 10, justifyContent: 'center' }}>
          <button
            onClick={reset}
            style={{
              padding: '8px 18px',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--color-border)',
              background: 'var(--color-surface)',
              color: 'var(--color-text-primary)',
              fontSize: 14,
              fontWeight: 500,
              cursor: 'pointer',
              fontFamily: 'var(--font-body)',
            }}
          >
            Reintentar
          </button>
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
            Ir al catálogo
          </Link>
        </div>
      </div>
    </main>
  )
}
