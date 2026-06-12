# WO-003: Data Layer

**Phase:** 1  
**Effort:** M  
**Status:** Complete  
**Related:** [FRD-001](../FRD-001-data-layer.md), [BP-003](../blueprints/BP-003-data-flow.md)  
**Prerequisites:** WO-001 (project scaffold)

---

## Objective

Implement `lib/types.ts`, `lib/data.ts`, `lib/filters.ts`, and `lib/slugs.ts`.
These are the server-side data access functions consumed by all page Server Components.

---

## Tasks

### Task 1: Implement `lib/types.ts`

Copy the TypeScript types from BP-003 Data Flow spec:
- `Item`, `ItemImage`, `ItemExtra`
- `Cluster`, `Facets`, `FacetOption`
- `SortKey`, `FilterParams`

### Task 2: Implement `lib/data.ts` — core reading and grouping

```typescript
import fs from 'fs'
import path from 'path'
import type { Item, Cluster, Facets } from './types'

// Path is relative to web-next/ (process.cwd() in Next.js)
const ITEMS_PATH = path.join(process.cwd(), '..', 'data', 'items.jsonl')

let _cache: Cluster[] | null = null

function readRawItems(): Item[] {
  const raw = fs.readFileSync(ITEMS_PATH, 'utf-8')
  return raw.split('\n').filter(Boolean).flatMap(line => {
    try { return [JSON.parse(line) as Item] }
    catch { return [] }
  })
}

function compareVolumes(a?: string, b?: string): number {
  if (!a && !b) return 0
  if (!a) return 1  // no volume → end
  if (!b) return -1
  const numA = parseFloat(a)
  const numB = parseFloat(b)
  if (!isNaN(numA) && !isNaN(numB)) return numA - numB
  return a.localeCompare(b)
}

function buildCluster(items: Item[]): Cluster {
  const sorted = [...items].sort((a, b) => (b.score || 0) - (a.score || 0))
  const canonical = sorted[0]
  const volumes = new Set(items.map(i => i.volume).filter(Boolean))
  
  return {
    clusterKey: canonical.cluster_key,
    slug: canonical.slug,
    canonical,
    items,
    editionKey: canonical.edition_key,
    editionDisplay: canonical.edition_display,
    seriesDisplay: canonical.series_display,
    volume: canonical.volume,
    volumeCount: volumes.size || 1,
    signalTypes: [...new Set(items.flatMap(i => i.signal_types || []))],
    countries: [...new Set(items.map(i => i.country).filter((c): c is string => Boolean(c)))],
    publishers: [...new Set(items.map(i => i.publisher).filter((p): p is string => Boolean(p)))],
    languages: [...new Set(items.map(i => i.language).filter((l): l is string => Boolean(l)))],
  }
}

export function loadClusters(): Cluster[] {
  if (process.env.NODE_ENV === 'production' && _cache) return _cache
  
  const items = readRawItems()
  const groups = new Map<string, Item[]>()
  for (const item of items) {
    const key = item.cluster_key
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(item)
  }
  
  const clusters = Array.from(groups.values()).map(buildCluster)
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

### Task 3: Implement `lib/filters.ts`

```typescript
import type { Cluster, FilterParams, SortKey, Facets, FacetOption } from './types'

const LIMITED_SIGNALS = new Set([
  'limited', 'special_edition', 'collector', 'lore_edition',
  'variant_cover', 'artbook', 'kanzenban', 'deluxe', 'box_set',
  'retailer_exclusive',
])

export function parseFilterParams(params: Record<string, string | string[]>): FilterParams {
  const getArr = (key: string) => {
    const v = params[key]
    if (!v) return undefined
    return Array.isArray(v) ? v : [v]
  }
  
  return {
    q: params.q as string | undefined,
    country: getArr('country'),
    language: getArr('language'),
    publisher: getArr('publisher'),
    product_type: getArr('product_type'),
    source_class: getArr('source_class'),
    signal_types: getArr('signal_types'),
    min_score: params.min_score ? Number(params.min_score) : undefined,
    only_limited: params.only_limited === 'true',
    sort: (params.sort as SortKey) || 'score_desc',
    page: params.page ? Number(params.page) : 1,
  }
}

export function filterClusters(clusters: Cluster[], params: FilterParams): Cluster[] {
  return clusters.filter(c => {
    const item = c.canonical
    
    // Full-text search
    if (params.q) {
      const q = params.q.toLowerCase()
      const searchable = [item.title, item.title_original, item.series_display]
        .filter(Boolean).join(' ').toLowerCase()
      if (!searchable.includes(q)) return false
    }
    
    // Array filters (ANY match)
    if (params.country?.length && !params.country.some(v => c.countries.includes(v))) return false
    if (params.language?.length && !params.language.some(v => c.languages.includes(v))) return false
    if (params.publisher?.length && !params.publisher.some(v => c.publishers.includes(v))) return false
    
    if (params.product_type?.length) {
      const types = c.items.map(i => i.product_type).filter(Boolean)
      if (!params.product_type.some(v => types.includes(v))) return false
    }
    
    if (params.source_class?.length) {
      const classes = c.items.map(i => i.source_class).filter(Boolean)
      if (!params.source_class.some(v => classes.includes(v))) return false
    }
    
    // Signal types (ALL must be present)
    if (params.signal_types?.length) {
      if (!params.signal_types.every(s => c.signalTypes.includes(s))) return false
    }
    
    // Min score
    if (params.min_score && (item.score || 0) < params.min_score) return false
    
    // Only limited
    if (params.only_limited && !c.signalTypes.some(s => LIMITED_SIGNALS.has(s))) return false
    
    return true
  })
}

export function sortClusters(clusters: Cluster[], sort: SortKey = 'score_desc'): Cluster[] {
  return [...clusters].sort((a, b) => {
    switch (sort) {
      case 'score_desc': return (b.canonical.score || 0) - (a.canonical.score || 0)
      case 'score_asc':  return (a.canonical.score || 0) - (b.canonical.score || 0)
      case 'date_desc': {
        const da = a.canonical.release_date || ''
        const db = b.canonical.release_date || ''
        if (!da && !db) return 0
        if (!da) return 1
        if (!db) return -1
        return db.localeCompare(da)
      }
      case 'date_asc': {
        const da = a.canonical.release_date || ''
        const db = b.canonical.release_date || ''
        if (!da && !db) return 0
        if (!da) return 1
        if (!db) return -1
        return da.localeCompare(db)
      }
      case 'title_asc':
        return (a.canonical.title || '').localeCompare(b.canonical.title || '')
      case 'title_desc':
        return (b.canonical.title || '').localeCompare(a.canonical.title || '')
      default: return 0
    }
  })
}

export function paginate<T>(items: T[], page: number, pageSize = 60) {
  const total = items.length
  const pages = Math.ceil(total / pageSize)
  const safeP = Math.max(1, Math.min(page, pages || 1))
  const start = (safeP - 1) * pageSize
  return {
    items: items.slice(start, start + pageSize),
    total,
    pages,
    page: safeP,
  }
}

export function buildFacets(clusters: Cluster[]): Facets {
  const count = (values: string[]) => {
    const map = new Map<string, number>()
    for (const v of values) map.set(v, (map.get(v) || 0) + 1)
    return Array.from(map.entries())
      .map(([value, count]) => ({ value, count }))
      .sort((a, b) => b.count - a.count)
  }
  
  const scores = clusters.map(c => c.canonical.score || 0)
  
  return {
    countries: count(clusters.flatMap(c => c.countries)),
    languages: count(clusters.flatMap(c => c.languages)),
    publishers: count(clusters.flatMap(c => c.publishers)),
    productTypes: count(clusters.flatMap(c =>
      c.items.map(i => i.product_type).filter((t): t is string => Boolean(t))
    )),
    sourceClasses: count(clusters.flatMap(c =>
      c.items.map(i => i.source_class).filter((s): s is string => Boolean(s))
    )),
    signalTypes: count(clusters.flatMap(c => c.signalTypes)),
    scoreRange: {
      min: Math.min(...scores),
      max: Math.max(...scores),
    },
  }
}
```

### Task 4: Write tests for data layer

Create `web-next/__tests__/data.test.ts`:

```typescript
import { filterClusters, sortClusters, paginate } from '@/lib/filters'
// Use a small fixture of 10 clusters

describe('filterClusters', () => {
  it('filters by query string', ...)
  it('filters by country (ANY match)', ...)
  it('filters by signal_types (ALL required)', ...)
  it('filters by min_score', ...)
  it('only_limited shows only limited editions', ...)
})

describe('sortClusters', () => {
  it('sorts by score_desc by default', ...)
  it('items without release_date go last in date sort', ...)
})

describe('paginate', () => {
  it('returns correct slice for page 2', ...)
  it('returns total and pages counts', ...)
  it('clamps page to valid range', ...)
})
```

### Task 5: Smoke test with real data

```typescript
// Run in Node.js context to verify:
// cd web-next && node -e "
//   const { loadClusters } = require('./lib/data')
//   const clusters = loadClusters()
//   console.log('Clusters:', clusters.length)
//   console.log('First:', clusters[0].slug, clusters[0].canonical.title)
// "
```

---

## Files Created/Modified

- `web-next/lib/types.ts`
- `web-next/lib/data.ts`
- `web-next/lib/filters.ts`
- `web-next/lib/slugs.ts` (re-exports from data.ts for convenience)
- `web-next/__tests__/data.test.ts`

---

## Acceptance Criteria

- [x] `loadClusters()` returns the correct number of clusters (= distinct cluster_keys in items.jsonl) — **10038 clusters from 10103 items** (65 items excluded: no `standardized_at`)
- [x] `filterClusters` with `q="berserk"` returns only Berserk items
- [x] `filterClusters` with `signal_types=["box_set"]` returns only box set clusters
- [x] `paginate` with page=2, pageSize=60 returns items 61–120
- [x] `buildFacets` returns non-empty arrays for all facet categories
- [x] No TypeScript errors (`npm run type-check`)
- [x] All filter tests pass — **17/17 tests pass**

**Completed 2026-05-27.** Changes:
- `lib/data.ts`: added `.filter(item => Boolean(item.standardized_at))` in `readRawItems()` (FR-1b)
- `lib/slugs.ts`: created as thin re-export of `allSlugs`, `allEditionKeys`, `clusterBySlug` from `./data`
- `vitest.config.ts`: vitest configured with `@/*` path alias
- `package.json`: added `test` (vitest run) and `type-check` (tsc --noEmit) scripts
- `__tests__/data.test.ts`: 17 tests covering `filterClusters`, `sortClusters`, `paginate`
