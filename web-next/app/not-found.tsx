import Link from 'next/link'
import { SearchX } from 'lucide-react'

// Antes: 404 default de Next (en inglés, sin header, sin link de vuelta) —
// las ~23k páginas de detalle usan dynamicParams=false, así que cualquier
// slug viejo/typo (los slugs pueden cambiar con re-scrapes) caía acá
// (auditoría #7). El Header (con buscador) sigue montado vía el root layout.
export default function NotFound() {
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
      <SearchX size={48} strokeWidth={1.5} style={{ color: 'var(--ink-300)' }} />
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
          Página no encontrada
        </h1>
        <p style={{ fontSize: 14, color: 'var(--color-text-secondary)', maxWidth: 420, marginBottom: 20 }}>
          Esta ficha, edición o serie no existe (o cambió de dirección en un
          re-scrape reciente). Probá buscarla desde el catálogo.
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
          Ir al catálogo
        </Link>
      </div>
    </main>
  )
}
