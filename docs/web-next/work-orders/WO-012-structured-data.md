# WO-012: Structured Data (JSON-LD)

**Phase:** 5
**Effort:** M
**Status:** Complete (2026-06-06)
**Related:** [FRD-008](../FRD-008-seo-discoverability.md) FR-8
**Prerequisites:** WO-009 (site URL), WO-011 (descriptions), WO-010 (metadata)

---

## Objective

Emit schema.org JSON-LD on every route so search engines get rich results and LLMs can
reliably extract catalog facts (ISBN, author, publisher, price, edition type). This is
the single highest-leverage step for LLM discoverability — structured facts beat prose.

---

## Tasks

### Task 1: `<JsonLd>` component

`components/seo/JsonLd.tsx` — server component, safe serialization:
```tsx
export function JsonLd({ data }: { data: object | object[] }) {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(data).replace(/</g, '\\u003c') }}
    />
  )
}
```

### Task 2: `lib/jsonld.ts` builders

```ts
import { absoluteUrl } from '@/lib/seo'
import { itemDescription } from '@/lib/descriptions'
import type { Cluster, Series } from '@/lib/types'

const availability = (c: Cluster['canonical']) =>
  c.stock_type === 'out_of_stock' ? 'https://schema.org/OutOfStock'
  : c.rarity === 'super_rare' ? 'https://schema.org/LimitedAvailability'
  : 'https://schema.org/InStock'

export function itemJsonLd(cluster: Cluster, slug: string) {
  const c = cluster.canonical
  const url = absoluteUrl(`/item/${slug}`)
  const image = c.image_local ? absoluteUrl(c.image_local) : c.image_url
  return {
    '@context': 'https://schema.org',
    '@type': c.isbn ? ['Product', 'Book'] : 'Product',
    name: c.title,
    description: itemDescription(cluster),
    image,
    url,
    ...(c.isbn && { isbn: c.isbn, bookFormat: 'https://schema.org/Hardcover' }),
    ...(c.author && { author: { '@type': 'Person', name: c.author } }),
    ...(c.publisher && { publisher: { '@type': 'Organization', name: c.publisher } }),
    ...(c.release_date && { datePublished: c.release_date }),
    ...(c.language && { inLanguage: c.language }),
  }
}

export function breadcrumbJsonLd(trail: { name: string; path: string }[]) {
  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: trail.map((t, i) => ({
      '@type': 'ListItem', position: i + 1, name: t.name, item: absoluteUrl(t.path),
    })),
  }
}

export function itemListJsonLd(name: string, items: { name: string; path: string }[]) {
  return {
    '@context': 'https://schema.org',
    '@type': 'CollectionPage',
    name,
    mainEntity: {
      '@type': 'ItemList',
      itemListElement: items.map((it, i) => ({
        '@type': 'ListItem', position: i + 1, name: it.name, url: absoluteUrl(it.path),
      })),
    },
  }
}

export function websiteJsonLd() {
  return {
    '@context': 'https://schema.org',
    '@type': 'WebSite',
    name: 'PandaWatch',
    url: absoluteUrl('/'),
    potentialAction: {
      '@type': 'SearchAction',
      target: { '@type': 'EntryPoint', urlTemplate: absoluteUrl('/?q={query}') },
      'query-input': 'required name=query',
    },
  }
}
```

### Task 3: Inject per route

- **Root layout** → `<JsonLd data={[websiteJsonLd(), organizationJsonLd()]} />`.
- **`/item`** → `<JsonLd data={[itemJsonLd(cluster, slug), breadcrumbJsonLd([...])]} />`
  (breadcrumb: Home → Series → Edition → Item, using known display names + paths).
- **`/edition`** → `itemListJsonLd(editionName, volumes→/item/slug)` + breadcrumb.
- **`/series`** → `itemListJsonLd(seriesName, editions→/edition/key)` + breadcrumb.

---

## Files Created/Modified

- `web-next/components/seo/JsonLd.tsx` (new)
- `web-next/lib/jsonld.ts` (new)
- `web-next/app/layout.tsx`, `app/item/[slug]/page.tsx`, `app/edition/[editionKey]/page.tsx`, `app/series/[seriesKey]/page.tsx`

---

## Notes (implementation)

- `<JsonLd data={[...]}>` emits one `<script>` per route containing an **array** of
  schema objects. Each route inherits the layout's `[WebSite, Organization]` plus its own.
- Item is `['Product','Book']` only when it has an ISBN; otherwise plain `Product`.
- **Known data artifact:** the `author` field can carry an "Autori:/Autores:" prefix from
  scraping (surfaces in the Person name). Same class as the read-more boilerplate — fix
  belongs in the Python extractor/retrofit (tracked alongside the description cleanup task).

## Acceptance Criteria

- [x] Each route emits valid JSON-LD (all blocks `JSON.parse` clean; `<` escaped).
- [x] Item with ISBN → `Product+Book` with availability/url.
      Verified on `/item/jiro-taniguchi-collection-panini-deluxe-2`.
- [x] Edition and series emit `CollectionPage` + `ItemList`.
- [x] `BreadcrumbList` present on item, edition, series.
- [x] `WebSite` (+ `SearchAction`) and `Organization` present site-wide.
- [x] `tsc --noEmit` clean; dev server logs no errors.
- [ ] Post-deploy: validate sampled URLs in Google Rich Results Test (needs public domain).

---

## Verification

`preview_eval` to read `document.querySelectorAll('script[type="application/ld+json"]')`
content per route and `JSON.parse` each. Post-deploy, run the URLs through Google Rich
Results Test and Schema.org validator.
