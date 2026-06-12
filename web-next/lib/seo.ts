/**
 * SEO helpers — absolute origin resolution for sitemap, canonical, OG tags.
 *
 * Resolution order (FRD-008 FR-1, D1):
 *   1. NEXT_PUBLIC_SITE_URL  — explicit prod domain (https://watch.pandatrack.app)
 *   2. VERCEL_PROJECT_PRODUCTION_URL / VERCEL_URL — Vercel-injected, scheme-less,
 *      so preview deploys self-canonicalize
 *   3. http://localhost:3000 — dev fallback
 */

const FALLBACK = 'http://localhost:3000'

export function siteUrl(): string {
  const explicit = process.env.NEXT_PUBLIC_SITE_URL
  if (explicit) return explicit.replace(/\/$/, '')

  const vercel = process.env.VERCEL_PROJECT_PRODUCTION_URL ?? process.env.VERCEL_URL
  if (vercel) return `https://${vercel.replace(/\/$/, '')}`

  return FALLBACK
}

export function absoluteUrl(path = '/'): string {
  return `${siteUrl()}${path.startsWith('/') ? path : `/${path}`}`
}

// ─── Route paths ──────────────────────────────────────────────────────────────
// Única fuente de construcción de rutas internas: las claves pueden traer
// caracteres no-ASCII (CJK, homoglifos), así que SIEMPRE van percent-encoded
// — un <loc> del sitemap con el carácter crudo es inválido y la página
// 404-ea si el link no coincide con el param decodificado.

export const seriesPath = (key: string) => `/series/${encodeURIComponent(key)}`
export const editionPath = (key: string) => `/edition/${encodeURIComponent(key)}`
export const itemPath = (slug: string) => `/item/${encodeURIComponent(slug)}`

/**
 * Decodifica un segmento dinámico de ruta (Next lo entrega percent-encoded).
 * Sin esto, `/series/...%E7%95%AA` no matchea la clave real y da 404 falso.
 */
export function decodeRouteParam(value: string): string {
  try {
    return decodeURIComponent(value)
  } catch {
    return value
  }
}

/**
 * Build an OpenGraph image entry from a remote URL or a local mirror filename.
 * Returns [] when no image, so it can be spread into `openGraph.images`.
 *
 * - `http(s)://…`        → used as-is
 * - `/path`              → resolved against the site origin
 * - bare `filename.jpg`  → the local mirror, served at `/images/<filename>`
 *
 * Sin width/height: las dimensiones reales no se conocen y declararlas
 * inventadas es peor que omitirlas.
 */
export function ogImage(value?: string | null, alt?: string) {
  if (!value) return []
  let url: string
  if (value.startsWith('http')) url = value
  else if (value.startsWith('/')) url = absoluteUrl(value)
  else url = absoluteUrl(`/images/${value}`)
  return [{ url, alt: alt ?? 'PandaWatch' }]
}
