# WO-009: SEO Foundations — Site URL, robots, sitemap, manifest

**Phase:** 5
**Effort:** S
**Status:** Complete (2026-06-06)
**Related:** [FRD-008](../FRD-008-seo-discoverability.md) FR-1, FR-2, FR-3, FR-4, FR-7
**Prerequisites:** WO-004 (catalog), WO-005 (edition), WO-006 (item), WO-008 (series) — all routes live

---

## Objective

Stand up the crawl-entry surfaces: an absolute site-URL helper, `robots.txt`, a
segmented `sitemap.xml`, and a web manifest. This is the highest-ROI work and unblocks
everything else (canonical/OG all need the site URL). No other WO depends on the final
domain except production deploy.

---

## Tasks

### Task 1: Site URL helper + env var

`lib/seo.ts` — resolution order: explicit env var → Vercel-injected URLs → localhost.
Vercel auto-sets `VERCEL_PROJECT_PRODUCTION_URL` (prod) and `VERCEL_URL` (per-deploy)
without scheme, so preview deploys self-canonicalize and prod uses the real domain.
```ts
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
```

Add to `.env.example` (repo root or `web-next/.env.example`, match existing convention):
```
# Public origin of the deployed Next.js app — used for sitemap, canonical, OG tags.
# On Vercel this is optional: falls back to VERCEL_PROJECT_PRODUCTION_URL / VERCEL_URL.
# Production domain:
NEXT_PUBLIC_SITE_URL=https://watch.pandatrack.app
```
> Set `NEXT_PUBLIC_SITE_URL=https://watch.pandatrack.app` in Vercel's **Production**
> environment. Preview deploys can leave it unset — they self-canonicalize off
> Vercel's injected `VERCEL_URL`.

### Task 2: `app/robots.ts`

```ts
import type { MetadataRoute } from 'next'
import { absoluteUrl } from '@/lib/seo'

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: '*',
        allow: '/',
        // Block faceted/duplicate catalog URLs (FR-7). Detail pages stay open.
        disallow: ['/?', '/*?filter=', '/*?sort=', '/*?page=', '/*?q='],
      },
      // AI / answer-engine crawlers are an intended channel — explicitly allowed.
      { userAgent: ['GPTBot', 'ClaudeBot', 'anthropic-ai', 'PerplexityBot', 'Google-Extended', 'CCBot', 'cohere-ai'], allow: '/' },
    ],
    sitemap: absoluteUrl('/sitemap.xml'),
    host: absoluteUrl('/'),
  }
}
```

### Task 3: `app/sitemap.ts` (single file)

**Decision (implementation):** a single sitemap. The standardized corpus is **19,214
URLs** (1 home + 3,220 series + 5,659 editions + 10,334 items as of 2026-06-06) — well
under the 50,000-URL / 50 MB limit, so segmentation via `generateSitemaps()` would add
the sitemap-index question for no benefit. Revisit and split per entity only when the
corpus approaches ~50k.
```ts
import type { MetadataRoute } from 'next'
import { absoluteUrl } from '@/lib/seo'
import { allSeriesKeys, allEditionKeys, allSlugs } from '@/lib/data'

export default function sitemap(): MetadataRoute.Sitemap {
  const home = [{ url: absoluteUrl('/'), changeFrequency: 'daily', priority: 1 }]
  const series = allSeriesKeys().map(k => ({ url: absoluteUrl(`/series/${k}`), changeFrequency: 'weekly', priority: 0.8 }))
  const editions = allEditionKeys().map(k => ({ url: absoluteUrl(`/edition/${k}`), changeFrequency: 'weekly', priority: 0.7 }))
  const items = allSlugs().map(s => ({ url: absoluteUrl(`/item/${s}`), changeFrequency: 'monthly', priority: 0.6 }))
  return [...home, ...series, ...editions, ...items]
}
```

### Task 4: `app/manifest.ts`

```ts
import type { MetadataRoute } from 'next'

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: 'PandaWatch — Ediciones especiales de manga',
    short_name: 'PandaWatch',
    description: 'Descubrí ediciones especiales de manga: deluxe, box sets, limited, artbooks.',
    start_url: '/',
    display: 'standalone',
    background_color: '#0d0d0f',
    theme_color: '#0d0d0f',
    icons: [
      { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
      { src: '/icon-512.png', sizes: '512x512', type: 'image/png' },
    ],
  }
}
```
Add the two PNG icons under `web-next/public/` (export from the existing logo/favicon).

### Task 5: Crawl hygiene on home (FR-7)

In `app/page.tsx` `generateMetadata` (added in WO-010), when `searchParams` are non-empty,
return `robots: { index: false, follow: true }` and `alternates.canonical: absoluteUrl('/')`.
(Implemented together with WO-010; noted here as the robots counterpart.)

---

## Files Created/Modified

- `web-next/lib/seo.ts` (new)
- `web-next/app/robots.ts` (new)
- `web-next/app/sitemap.ts` (new)
- `web-next/app/manifest.ts` (new)
- `web-next/public/icon-192.png`, `icon-512.png` (new)
- `.env.example` (new env var)

---

## Acceptance Criteria

- [x] `/robots.txt` returns rules + sitemap line; AI crawlers (GPTBot, ClaudeBot, …) allowed; `/*?` disallowed.
- [x] `/sitemap.xml` is `application/xml`, 200; sampled URLs absolute. 19,214 URLs (1 + 3,220 series + 5,659 edition + 10,334 item).
- [x] Single sitemap under the 50,000-URL limit.
- [x] `/manifest.webmanifest` resolves 200 with 192/512 icons (+ maskable).
- [x] `siteUrl()` resolves `NEXT_PUBLIC_SITE_URL` → Vercel URLs → localhost.
- [x] `tsc --noEmit` clean; dev server logs no errors on the new routes.

---

## Verification

Use the preview workflow: `preview_start`, then `preview_network` / fetch
`/robots.txt`, `/sitemap.xml`, `/manifest.webmanifest` and confirm 200 + content.
