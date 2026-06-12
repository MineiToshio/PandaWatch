# BP-003: Data Flow & Server Rendering

**Version:** 1.0  
**Status:** Draft  
**Author:** Architecture session 2026-05-27  
**Related FRDs:** FRD-001, FRD-003

---

## Purpose

Detail the exact data flow from `data/items.jsonl` on disk to rendered HTML in the
browser, including the TypeScript types at each stage, caching behavior, and the
boundary between server and client.

---

## Stage 1: Raw JSONL → Typed Items

```typescript
// lib/data.ts

import fs from 'fs'
import path from 'path'

const ITEMS_PATH = path.join(process.cwd(), '..', 'data', 'items.jsonl')

function readRawItems(): Item[] {
  const raw = fs.readFileSync(ITEMS_PATH, 'utf-8')
  return raw
    .split('\n')
    .filter(Boolean)
    .flatMap(line => {
      try { return [JSON.parse(line) as Item] }
      catch { console.warn('Skipping malformed line'); return [] }
    })
}
```

**Notes:**
- `process.cwd()` in Next.js = `web-next/` directory
- `..` navigates to the repo root, then `data/items.jsonl`
- `fs` is only available in Server Components (not in Client Components)
- In development, Next.js does not cache `fs.readFileSync` between requests
  (every request re-reads the file — reflects scraper updates instantly)
- In production static export, this runs once at build time

---

## Stage 2: Items → Clusters

```typescript
// lib/data.ts

function groupIntoClusters(items: Item[]): Cluster[] {
  const groups = new Map<string, Item[]>()
  
  for (const item of items) {
    const key = item.cluster_key
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(item)
  }
  
  return Array.from(groups.values()).map(buildCluster)
}

// ⚠️ Actualizado 2026-06-01: el score se eliminó de la UI y del ordenamiento.
// El canónico ya NO se elige por score sino por COMPLETITUD (ISBN > imagen >
// precio). Los tipos abajo conservan el snippet original por referencia
// histórica, pero en el código real: Item ya no tiene `score`, Facets ya no
// tiene `scoreRange`, SortKey ya no tiene `score_desc`/`score_asc`, y
// FilterParams ya no tiene `min_score`. El default de sort es `date_desc`.
function buildCluster(items: Item[]): Cluster {
  // canonical = item más completo (ISBN > imagen > precio); antes: highest score
  const canonical = items.sort((a, b) => b.score - a.score)[0]
  
  return {
    clusterKey: canonical.cluster_key,
    slug: canonical.slug,
    canonical,
    items,
    editionKey: canonical.edition_key,
    editionDisplay: canonical.edition_display,
    seriesDisplay: canonical.series_display,
    volume: canonical.volume,
    volumeCount: new Set(items.map(i => i.volume).filter(Boolean)).size || 1,
    signalTypes: [...new Set(items.flatMap(i => i.signal_types || []))],
    countries: [...new Set(items.map(i => i.country).filter(Boolean))],
    publishers: [...new Set(items.map(i => i.publisher).filter(Boolean))],
    languages: [...new Set(items.map(i => i.language).filter(Boolean))],
  }
}
```

**Key decisions:**
- `canonical` = item with highest `score` in the cluster
- `signalTypes`, `countries`, `publishers`, `languages` = union across all cluster items
- `volumeCount` = count of distinct non-null volumes (used for stack CSS leaves)
- Missing `slug` is a soft error — the item renders but without a detail link

---

## Stage 3: Public API (exported functions)

```typescript
// lib/data.ts — public API

let _cache: Cluster[] | null = null

export function loadClusters(): Cluster[] {
  // In production: clusters are computed once at module load (static build)
  // In development: re-read on every call (hot reload behavior)
  if (process.env.NODE_ENV === 'production' && _cache) return _cache
  const items = readRawItems()
  const clusters = groupIntoClusters(items)
  if (process.env.NODE_ENV === 'production') _cache = clusters
  return clusters
}

export function loadEditionClusters(editionKey: string): Cluster[] {
  return loadClusters()
    .filter(c => c.editionKey === editionKey)
    .sort((a, b) => compareVolumes(a.volume, b.volume))
}

export function clusterBySlug(slug: string): Cluster | null {
  return loadClusters().find(c => c.slug === slug) ?? null
}

export function allEditionKeys(): string[] {
  return [...new Set(
    loadClusters()
      .map(c => c.editionKey)
      .filter((k): k is string => Boolean(k))
  )]
}

export function allSlugs(): string[] {
  return loadClusters()
    .map(c => c.slug)
    .filter((s): s is string => Boolean(s))
}
```

---

## Stage 4: Server Component → HTML

### Catalog page

```tsx
// app/page.tsx — Server Component (no "use client")

export default async function CatalogPage({
  searchParams
}: {
  searchParams: Promise<Record<string, string | string[]>>
}) {
  const params = await searchParams
  const allClusters = loadClusters()
  const facets = buildFacets(allClusters)           // from unfiltered corpus
  
  const filtered = filterClusters(allClusters, parseFilterParams(params))
  const sorted = sortClusters(filtered, params.sort as SortKey)
  const { items, total, pages, page } = paginate(sorted, Number(params.page) || 1)

  return (
    <div className="layout-catalog">
      <SidebarFilters facets={facets} current={params} />   {/* "use client" */}
      <main>
        <SortBar total={total} sort={params.sort} />
        <CatalogGrid clusters={items} />
        <Pagination total={pages} current={page} />
      </main>
    </div>
  )
}
```

The Server Component:
1. Reads and filters data (server-only)
2. Renders static HTML for the grid (no JS needed for the cards)
3. Passes pre-computed `facets` to `SidebarFilters` (Client Component)
   so the sidebar doesn't need to fetch anything

### What goes to the browser

- **Static HTML:** All edition cards, images, titles, badges
- **JavaScript bundle:** Only what `SidebarFilters`, `ImageCarousel`,
  and `ThemeToggle` need
- **No JSONL in the browser:** The data never leaves the server

---

## Stage 5: Client Component → URL update

```tsx
// components/catalog/SidebarFilters.tsx — "use client"

'use client'
import { useRouter, useSearchParams } from 'next/navigation'
import { useCallback } from 'react'

export function SidebarFilters({ facets, current }) {
  const router = useRouter()
  const searchParams = useSearchParams()

  const updateFilter = useCallback((key: string, value: string | string[]) => {
    const params = new URLSearchParams(searchParams.toString())
    // ... update params ...
    router.replace(`/?${params.toString()}`, { scroll: false })
  }, [router, searchParams])

  // render filter UI...
}
```

The URL update triggers a server re-render of the catalog page with the new
`searchParams`. Next.js handles this efficiently via partial rendering.

---

## Caching Strategy

| Context | Behavior |
|---|---|
| `next dev` | `fs.readFileSync` on every request; JSONL changes reflected immediately |
| `next build` (static export) | Data read once; pages baked into HTML at build time |
| `next start` (server) | Module-level `_cache` prevents re-reading JSONL per request |
| After scraper run | Run `next build` to pick up new items; or in future, use ISR with `revalidate` |

---

## TypeScript Types Reference

```typescript
// lib/types.ts

export type Item = {
  url: string
  slug?: string
  title: string
  title_original?: string
  series_key?: string
  series_display?: string
  edition_key?: string
  edition_display?: string
  volume?: string
  cluster_key: string
  signal_types?: string[]
  score: number
  country?: string
  publisher?: string
  language?: string
  product_type?: string
  source_class?: string
  isbn?: string
  author?: string
  release_date?: string
  detected_at?: string
  standardized_at?: string
  image_url?: string
  image_local?: string
  images?: ItemImage[]
  extras?: ItemExtra[]
  source?: string
  stock_type?: string
}

export type ItemImage = {
  url: string
  local?: string
  kind: 'cover' | 'gallery' | 'extra' | 'variant_cover' | 'back_cover'
  description?: string
}

export type ItemExtra = {
  description: string
  release_date?: string
  source_section?: string
}

export type Cluster = {
  clusterKey: string
  slug?: string
  canonical: Item
  items: Item[]
  editionKey?: string
  editionDisplay?: string
  seriesDisplay?: string
  volume?: string
  volumeCount: number
  signalTypes: string[]
  countries: string[]
  publishers: string[]
  languages: string[]
}

export type Facets = {
  countries: FacetOption[]
  languages: FacetOption[]
  publishers: FacetOption[]
  productTypes: FacetOption[]
  sourceClasses: FacetOption[]
  signalTypes: FacetOption[]
  scoreRange: { min: number; max: number }
}

export type FacetOption = {
  value: string
  count: number
  label?: string     // display label if different from value
}

export type SortKey =
  | 'score_desc' | 'score_asc'
  | 'date_desc'  | 'date_asc'
  | 'title_asc'  | 'title_desc'

export type FilterParams = {
  q?: string
  country?: string[]
  language?: string[]
  publisher?: string[]
  product_type?: string[]
  source_class?: string[]
  signal_types?: string[]
  min_score?: number
  only_limited?: boolean
  sort?: SortKey
  page?: number
}
```
