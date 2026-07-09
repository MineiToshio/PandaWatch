'use client'

import { useCallback, useTransition } from 'react'
import { useRouter, usePathname, useSearchParams } from 'next/navigation'

/**
 * Mutación de URL params del catálogo — fuente única (auditoría #11). Antes
 * reimplementada 4 veces (SidebarFilters/SearchBar/SortBar/Pagination) con
 * matices propios: SortBar/Pagination leían el snapshot `useSearchParams()`
 * mientras SidebarFilters/SearchBar leían `window.location.search` a
 * propósito para no pisar un cambio en la misma ventana de render/debounce —
 * un bug latente si dos mutadores disparaban casi a la vez. Este hook SIEMPRE
 * lee la URL viva y borra `page` en cada mutación (salvo que la mutación SEA
 * de `page`, ver `set()`).
 *
 * Envuelve la navegación en `useTransition` (auditoría #7): `isPending`
 * permite que cada consumidor muestre un feedback discreto (opacity/spinner)
 * mientras el Server Component del catálogo re-renderiza — antes el filtro
 * quedaba "congelado" sin señal hasta que la respuesta volvía.
 */
export function useCatalogParams() {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const [isPending, startTransition] = useTransition()

  const live = useCallback(() => new URLSearchParams(window.location.search), [])

  const navigate = useCallback(
    (next: URLSearchParams, push = false) => {
      const qs = next.toString()
      const url = qs ? `${pathname}?${qs}` : pathname
      startTransition(() => {
        if (push) router.push(url)
        else router.replace(url)
      })
    },
    [pathname, router]
  )

  /** Setea (o borra, con value=null/'') un param escalar. Borra `page` salvo que key==='page'. */
  const set = useCallback(
    (key: string, value: string | null, opts?: { push?: boolean }) => {
      const next = live()
      if (value === null || value === '') next.delete(key)
      else next.set(key, value)
      if (key !== 'page') next.delete('page')
      navigate(next, opts?.push)
    },
    [live, navigate]
  )

  /** Agrega/quita un valor de un param multi-valor (checkboxes de filtro). */
  const toggle = useCallback(
    (key: string, value: string) => {
      const next = live()
      const existing = next.getAll(key)
      if (existing.includes(value)) {
        next.delete(key)
        existing.filter(v => v !== value).forEach(v => next.append(key, v))
      } else {
        next.append(key, value)
      }
      next.delete('page')
      navigate(next)
    },
    [live, navigate]
  )

  /** Limpia todos los filtros. keepSort conserva el orden elegido (no es un filtro). */
  const clearAll = useCallback(
    (opts?: { keepSort?: boolean }) => {
      const next = new URLSearchParams()
      if (opts?.keepSort) {
        const sort = live().get('sort')
        if (sort) next.set('sort', sort)
      }
      navigate(next)
    },
    [live, navigate]
  )

  /** Navegación cruda (p. ej. desde el detalle hacia `/?q=…`), misma transición compartida. */
  const goTo = useCallback(
    (url: string, opts?: { push?: boolean }) => {
      startTransition(() => {
        if (opts?.push === false) router.replace(url)
        else router.push(url)
      })
    },
    [router]
  )

  return { params: searchParams, pathname, isPending, live, set, toggle, clearAll, goTo }
}

export default useCatalogParams
