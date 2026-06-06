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

/**
 * Build an OpenGraph image entry from a remote URL or a local mirror filename.
 * Returns [] when no image, so it can be spread into `openGraph.images`.
 *
 * - `http(s)://…`        → used as-is
 * - `/path`              → resolved against the site origin
 * - bare `filename.jpg`  → the local mirror, served at `/images/<filename>`
 */
export function ogImage(value?: string | null, alt?: string) {
  if (!value) return []
  let url: string
  if (value.startsWith('http')) url = value
  else if (value.startsWith('/')) url = absoluteUrl(value)
  else url = absoluteUrl(`/images/${value}`)
  return [{ url, width: 800, height: 1200, alt: alt ?? 'PandaWatch' }]
}
