# WO-010: Rich Metadata — canonical, Open Graph, Twitter, home metadata

**Phase:** 5
**Effort:** M
**Status:** Complete (2026-06-06)
**Related:** [FRD-008](../FRD-008-seo-discoverability.md) FR-5, FR-7, FR-9
**Prerequisites:** WO-009 (site URL helper), WO-011 (descriptions)

---

## Objective

Upgrade page metadata across the app: root defaults, the missing home `generateMetadata`,
and full canonical + Open Graph + Twitter on series/edition/item. Descriptions come from
WO-011's `lib/descriptions.ts` (use a stub string if WO-011 lands later).

---

## Tasks

### Task 1: Root layout metadata (`app/layout.tsx`)

```ts
import { siteUrl } from '@/lib/seo'

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl()),
  title: {
    default: 'PandaWatch — Ediciones especiales de manga',
    template: '%s · PandaWatch',
  },
  description:
    'Descubrí ediciones especiales de manga de todo el mundo: deluxe, box sets, limited editions, artbooks, kanzenban y más.',
  applicationName: 'PandaWatch',
  openGraph: {
    siteName: 'PandaWatch',
    locale: 'es_ES',
    type: 'website',
  },
  twitter: { card: 'summary_large_image' },
  alternates: { canonical: '/' },
}

export const viewport = { themeColor: '#0d0d0f' }
```

### Task 2: Home metadata + filter hygiene (`app/page.tsx`)

Add `generateMetadata` (currently absent). Mark filtered views noindex (FR-7):
```ts
export async function generateMetadata({ searchParams }: { searchParams: Promise<Record<string,string>> }): Promise<Metadata> {
  const sp = await searchParams
  const filtered = Object.keys(sp).length > 0
  return {
    title: 'Catálogo de ediciones especiales de manga',
    description: 'Explorá miles de ediciones especiales de manga…',
    alternates: { canonical: '/' },
    robots: filtered ? { index: false, follow: true } : undefined,
  }
}
```

### Task 3: Shared OG/metadata helper (`lib/seo.ts` additions)

```ts
export function ogImage(localOrUrl?: string, alt?: string) {
  if (!localOrUrl) return []
  const url = localOrUrl.startsWith('http') ? localOrUrl : absoluteUrl(localOrUrl)
  return [{ url, width: 800, height: 1200, alt: alt ?? 'PandaWatch' }]
}
```

### Task 4: Extend `generateMetadata` on the three detail routes

For **`app/item/[slug]/page.tsx`** (and analogously edition/series), replace the minimal
metadata with:
```ts
export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params
  const cluster = clusterBySlug(slug)
  if (!cluster) return {}
  const { canonical } = cluster
  const title = canonical.title
  const description = itemDescription(cluster)          // from WO-011
  const path = `/item/${slug}`
  return {
    title,
    description,
    alternates: { canonical: path },
    openGraph: {
      type: 'website',                                   // 'product' fields added via JSON-LD in WO-012
      url: absoluteUrl(path),
      title, description,
      images: ogImage(canonical.image_local ?? canonical.image_url, title),
    },
    twitter: { card: 'summary_large_image', title, description },
  }
}
```
- **Edition** → `editionDescription(clusters)`, canonical `/edition/[editionKey]`.
- **Series** → `seriesDescription(series)`, canonical `/series/[seriesKey]`.

### Task 5: Cover alt text (FR-9)

In the shared cover component (e.g. `CoverImage`), default `alt` to a descriptive string
when callers don't pass one:
`${series_display}${edition_display ? ' — ' + edition_display : ''}${volume ? ' Vol. ' + volume : ''}`.
Audit call sites to stop passing bare `canonical.title` where the richer string is available.

---

## Files Created/Modified

- `web-next/app/layout.tsx`
- `web-next/app/page.tsx`
- `web-next/app/item/[slug]/page.tsx`
- `web-next/app/edition/[editionKey]/page.tsx`
- `web-next/app/series/[seriesKey]/page.tsx`
- `web-next/lib/seo.ts` (ogImage helper)
- cover component (alt text)

---

## Notes (implementation)

- **`metadataBase`** is set in the root layout from `siteUrl()`, so canonical / OG `url`
  use relative paths and Next resolves them to absolute. `themeColor` moved to the
  `viewport` export (Next 16 convention).
- **Home** inherits the root default title/description (cleaner than a bespoke string);
  `generateMetadata` only adds canonical `/` + `noindex,follow` when `searchParams` exist.
- **`ogImage()`** prefers the remote `image_url` over the local mirror (more reliable for
  crawlers; the `public/images` symlink may not resolve on Vercel) and prefixes bare
  mirror filenames with `/images/`.
- **OG `type`** kept as `website` (not `book`/`product`) — product/Book facts are carried
  by JSON-LD in WO-012, avoiding incomplete `og:book:*` tags.
- **Read-more sanitizer** added to `lib/descriptions.ts` (`READ_MORE_PREFIX`) to strip
  scraped "MÁS INFORMACIÓN" / "EN SAVOIR PLUS" boilerplate from meta + on-page text.
  Upstream data fix tracked separately (spawned task).

## Acceptance Criteria

- [x] `/item/[slug]` head shows `<title>… · PandaWatch`, canonical, og:title,
      og:description, og:image (absolute), twitter:card. Verified.
- [x] Home title = root default; `/?country=Japan` emits `noindex, follow` + canonical `/`.
- [x] OG images are absolute URLs (e.g. `https://www.anime-store.fr/…`, `https://img.sanctuary.fr/…`).
- [x] Cover `alt` is descriptive (call sites pass title/seriesDisplay — no filenames).
- [x] `tsc --noEmit` clean; no new eslint errors (pre-existing setState-in-effect warnings untouched).

---

## Verification

`preview_start`, `preview_eval document.querySelector('link[rel=canonical]').href` and
`document.querySelector('meta[property="og:image"]').content` on each route; confirm
absolute URLs. Spot-check social preview with a card validator post-deploy.
