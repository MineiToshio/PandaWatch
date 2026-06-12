'use client'

import { useEffect } from 'react'
import { usePathname, useSearchParams } from 'next/navigation'

export const NAV_COUNT_KEY = 'pw:navCount'
export const CATALOG_URL_KEY = 'pw:catalogUrl'

/**
 * Estado de navegación por pestaña (sessionStorage) para BackLink:
 *  - NAV_COUNT_KEY: cuántas rutas se visitaron — si > 1, history.back() se
 *    queda dentro del sitio.
 *  - CATALOG_URL_KEY: última URL del catálogo (con filtros/página) para que
 *    "volver al catálogo" desde un deep link restaure el último estado.
 * Render nulo; va en el layout dentro de <Suspense> (useSearchParams).
 */
export function NavigationTracker() {
  const pathname = usePathname()
  const searchParams = useSearchParams()

  useEffect(() => {
    try {
      const n = Number(sessionStorage.getItem(NAV_COUNT_KEY) ?? '0')
      sessionStorage.setItem(NAV_COUNT_KEY, String(n + 1))
    } catch { /* sessionStorage no disponible */ }
  }, [pathname])

  useEffect(() => {
    if (pathname !== '/') return
    try {
      const qs = searchParams.toString()
      sessionStorage.setItem(CATALOG_URL_KEY, qs ? `/?${qs}` : '/')
    } catch { /* sessionStorage no disponible */ }
  }, [pathname, searchParams])

  return null
}

export default NavigationTracker
