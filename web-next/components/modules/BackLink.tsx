'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { ChevronLeft } from 'lucide-react'
import { NAV_COUNT_KEY, CATALOG_URL_KEY } from './NavigationTracker'

type BackLinkProps = {
  fallbackHref: string
  label: string
}

/**
 * Botón "volver" sin estado en la URL. Antes el estado viajaba como ?from= en
 * cada link de card, lo que (a) anulaba la generación estática de las páginas
 * de detalle (searchParams en el server), (b) hacía los links internos
 * invisibles para crawlers (robots.txt bloquea /*?) y (c) permitía inyectar
 * hrefs externos. Ahora:
 *   - se server-renderiza como <a href={fallback}> limpio (crawleable),
 *   - al click, si hubo navegación interna previa, history.back() restaura el
 *     estado exacto del catálogo (filtros, página, scroll),
 *   - si se entró directo (deep link), navega al fallback; para el catálogo
 *     usa la última URL guardada por NavigationTracker si existe.
 */
export function BackLink({ fallbackHref, label }: BackLinkProps) {
  const router = useRouter()

  function handleClick(e: React.MouseEvent<HTMLAnchorElement>) {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
    try {
      const navCount = Number(sessionStorage.getItem(NAV_COUNT_KEY) ?? '0')
      if (navCount > 1) {
        e.preventDefault()
        router.back()
        return
      }
      if (fallbackHref === '/') {
        const saved = sessionStorage.getItem(CATALOG_URL_KEY)
        if (saved && saved !== '/') {
          e.preventDefault()
          router.push(saved)
        }
      }
    } catch {
      // sessionStorage no disponible → seguir el href normal
    }
  }

  return (
    <Link
      href={fallbackHref}
      onClick={handleClick}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        fontSize: 14,
        color: 'var(--color-text-secondary)',
        textDecoration: 'none',
        marginBottom: 24,
        transition: 'color var(--duration-fast)',
      }}
    >
      <ChevronLeft size={16} strokeWidth={2} aria-hidden="true" />
      {label}
    </Link>
  )
}

export default BackLink
