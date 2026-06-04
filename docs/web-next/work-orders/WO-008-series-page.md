# WO-008: Series Highlights & Series Page

**Phase:** 4
**Depends on:** WO-004 (catalog), WO-005 (edition), WO-006 (item)
**Implements:** [FRD-007](../FRD-007-series-highlights.md)
**Status:** Done (2026-06-03)

---

## Goal

Add the **series (obra)** level to web-next:

1. A `Series` aggregate + loaders in the data layer.
2. A "Obras destacadas" highlights strip on the home page.
3. A new `/series/[seriesKey]` page showing all editions of one work.

No Python changes, no schema changes. Pure web-next.

---

## Files

**New**
```
web-next/components/series/SeriesCard.tsx
web-next/components/series/SeriesHighlights.tsx
web-next/components/series/SeriesHeader.tsx
web-next/app/series/[seriesKey]/page.tsx
```

**Modified**
```
web-next/lib/types.ts        ← add `Series` type
web-next/lib/data.ts         ← add loadSeries / topSeries / seriesByKey / loadSeriesEditions / allSeriesKeys
web-next/app/page.tsx        ← render <SeriesHighlights /> on the default view
```

---

## Step 1 — `Series` type (`lib/types.ts`)

```ts
export type Series = {
  seriesKey: string
  seriesDisplay: string
  cover: { imageLocal?: string; imageUrl?: string }
  editionCount: number   // distinct edition_key
  itemCount: number      // distinct cluster_key (products)
  countries: string[]
  publishers: string[]
  signalTypes: string[]
  topRarity?: Item['rarity']
}
```

## Step 2 — Data layer (`lib/data.ts`)

Add below the existing cluster functions. Reuse `loadClusters()` (cached) and the
private `completeness()` helper.

```ts
const RARITY_ORDER = ['common', 'rare', 'super_rare', 'ultra_rare'] as const

function buildSeries(seriesKey: string, clusters: Cluster[]): Series {
  const editionKeys = new Set<string>()
  const clusterKeys = new Set<string>()
  const countries = new Set<string>()
  const publishers = new Set<string>()
  const signalTypes = new Set<string>()
  let cover: Series['cover'] = {}
  let bestCover = -1
  let topRarityIdx = -1

  for (const c of clusters) {
    if (c.editionKey) editionKeys.add(c.editionKey)
    clusterKeys.add(c.clusterKey)
    c.countries.forEach(v => countries.add(v))
    c.publishers.forEach(v => publishers.add(v))
    c.signalTypes.forEach(v => signalTypes.add(v))

    // Representative cover = most complete item that actually has an image
    const it = c.canonical
    const score = completeness(it)
    if ((it.image_local || it.image_url) && score > bestCover) {
      bestCover = score
      cover = { imageLocal: it.image_local, imageUrl: it.image_url }
    }
    const ri = it.rarity ? RARITY_ORDER.indexOf(it.rarity) : -1
    if (ri > topRarityIdx) topRarityIdx = ri
  }

  return {
    seriesKey,
    seriesDisplay: clusters[0].seriesDisplay || clusters[0].canonical.series_display || seriesKey,
    cover,
    editionCount: editionKeys.size,
    itemCount: clusterKeys.size,
    countries: [...countries],
    publishers: [...publishers],
    signalTypes: [...signalTypes],
    topRarity: topRarityIdx >= 0 ? RARITY_ORDER[topRarityIdx] : undefined,
  }
}

let _seriesCache: Series[] | null = null

export function loadSeries(): Series[] {
  if (process.env.NODE_ENV === 'production' && _seriesCache) return _seriesCache

  const bySeries = new Map<string, Cluster[]>()
  for (const c of loadClusters()) {
    const key = c.canonical.series_key
    if (!key) continue
    if (!bySeries.has(key)) bySeries.set(key, [])
    bySeries.get(key)!.push(c)
  }

  const collator = new Intl.Collator('es')
  const series = Array.from(bySeries.entries())
    .map(([key, clusters]) => buildSeries(key, clusters))
    // FRD-007 FR-2 ranking — keep this comparator isolated for easy retuning
    .sort((a, b) =>
      b.editionCount - a.editionCount ||
      b.itemCount - a.itemCount ||
      collator.compare(a.seriesDisplay, b.seriesDisplay)
    )

  if (process.env.NODE_ENV === 'production') _seriesCache = series
  return series
}

export function topSeries(limit = 12): Series[] {
  return loadSeries()
    .filter(s => s.cover.imageLocal || s.cover.imageUrl)
    .slice(0, limit)
}

export function seriesByKey(seriesKey: string): Series | null {
  return loadSeries().find(s => s.seriesKey === seriesKey) ?? null
}

export function loadSeriesEditions(seriesKey: string): Cluster[] {
  const clusters = loadClusters().filter(c => c.canonical.series_key === seriesKey)
  // Reuse the catalog's edition grouping, then order by edition richness then title
  return groupByEdition(clusters).sort((a, b) =>
    b.volumeCount - a.volumeCount ||
    (a.canonical.title || '').localeCompare(b.canonical.title || '')
  )
}

export function allSeriesKeys(): string[] {
  return loadSeries().map(s => s.seriesKey)
}
```

> Note: `Series` must be imported in the `import type { … }` line at the top of
> `lib/data.ts`.

## Step 3 — `SeriesCard` (`components/series/SeriesCard.tsx`)

Server Component. Compact work card; mirror `EditionCard`'s uniform-height pattern
but simpler (no stack effect).

- `<Link href={`/series/${series.seriesKey}`}>` wrapping the whole card.
- Cover: `CoverImage` with `fill`, `aspect-ratio: 2/3`, `background: var(--ink-100)`.
- Country flags (≤3) bottom-left over the cover (same markup as `EditionCard`).
- Info block (fixed height, e.g. 64px): series name (2-line clamp,
  `font-family: var(--font-display)`) + stats line in `--color-text-tertiary`:
  `` `${editionCount} ${editionCount === 1 ? 'edición' : 'ediciones'} · ${itemCount} ${itemCount === 1 ? 'tomo' : 'tomos'}` ``.
- Card width is controlled by the strip (Step 4) via `flex: 0 0 auto; width: …`.

## Step 4 — `SeriesHighlights` (`components/series/SeriesHighlights.tsx`)

Server Component.

```tsx
import { topSeries } from '@/lib/data'
import { SeriesCard } from './SeriesCard'

export function SeriesHighlights() {
  const series = topSeries(12)
  if (!series.length) return null

  return (
    <section style={{ padding: '20px 16px 4px', maxWidth: 1280, margin: '0 auto' }}>
      <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 700,
                   color: 'var(--color-text-primary)', margin: 0 }}>
        Obras destacadas
      </h2>
      <p style={{ fontSize: 13, color: 'var(--color-text-tertiary)', margin: '2px 0 12px' }}>
        Las series con más ediciones especiales en el catálogo.
      </p>
      <div style={{ display: 'flex', gap: 12, overflowX: 'auto', paddingBottom: 6,
                    scrollSnapType: 'x proximity' }}>
        {series.map(s => (
          <div key={s.seriesKey} style={{ flex: '0 0 auto', width: 156, scrollSnapAlign: 'start' }}>
            <SeriesCard series={s} />
          </div>
        ))}
      </div>
    </section>
  )
}
```

(Hide the scrollbar with a small CSS rule in `globals.css` if desired —
`.series-strip::-webkit-scrollbar { display: none }` — optional polish.)

## Step 5 — Wire into the home page (`app/page.tsx`)

Render the strip above `CatalogControls`, **only on the default view**:

```tsx
// after computing `fp`
const isDefaultView =
  !fp.q &&
  fp.page === 1 &&
  !fp.country?.length && !fp.language?.length && !fp.publisher?.length &&
  !fp.product_type?.length && !fp.source_class?.length &&
  !fp.signal_types?.length && !fp.rarity?.length && !fp.only_limited

return (
  <>
    {isDefaultView && <SeriesHighlights />}
    <CatalogControls /* …unchanged… */>
      <CatalogGrid clusters={items} from={catalogFrom} />
      {pages > 1 && <Pagination total={pages} current={page} />}
    </CatalogControls>
  </>
)
```

## Step 6 — `SeriesHeader` (`components/series/SeriesHeader.tsx`)

Server Component, modeled on `EditionHeader`. Takes `series: Series`. Renders:
cover thumbnail (64×96) via `CoverImage`, `<h1>` series name, a stats line
`"{editionCount} ediciones · {itemCount} tomos"` + country flags, and the union of
`signalTypes` as `SignalChip`s.

## Step 7 — Series page (`app/series/[seriesKey]/page.tsx`)

```tsx
import { notFound } from 'next/navigation'
import { seriesByKey, loadSeriesEditions, allSeriesKeys } from '@/lib/data'
import { SeriesHeader } from '@/components/series/SeriesHeader'
import { CatalogGrid } from '@/components/catalog/CatalogGrid'
import { BackLink } from '@/components/modules/BackLink'

type Props = {
  params: Promise<{ seriesKey: string }>
  searchParams: Promise<{ from?: string }>
}

export default async function SeriesPage({ params, searchParams }: Props) {
  const { seriesKey } = await params
  const { from } = await searchParams
  const series = seriesByKey(seriesKey)
  if (!series) notFound()

  const editions = loadSeriesEditions(seriesKey)

  return (
    <main style={{ maxWidth: 1280, margin: '0 auto', padding: '24px 16px 64px' }}>
      <BackLink href={from || '/'} label="Catálogo" />
      <SeriesHeader series={series} />
      <CatalogGrid clusters={editions} from={`/series/${seriesKey}`} />
    </main>
  )
}

export async function generateStaticParams() {
  return allSeriesKeys().map(seriesKey => ({ seriesKey }))
}

export async function generateMetadata({ params }: Props) {
  const { seriesKey } = await params
  const series = seriesByKey(seriesKey)
  if (!series) return {}
  return {
    title: `${series.seriesDisplay} — PandaWatch`,
    description: `${series.editionCount} ediciones · ${series.itemCount} tomos`,
    openGraph: { images: series.cover.imageUrl ? [series.cover.imageUrl] : [] },
  }
}
```

> `CatalogGrid` keys on `cluster.clusterKey`; that is unique within a series, so no
> key collisions. The `from=/series/{seriesKey}` makes edition/item back-links
> return here.

---

## Verification

Run the dev server and check:

1. `npm run type-check` → 0 errors.
2. Home page (`/`) shows "Obras destacadas" with 12 cards; One Piece is first.
3. Apply any filter or go to `?page=2` → the strip disappears.
4. Click the One Piece card → `/series/one-piece` shows the header (84 ediciones)
   + a grid of all One Piece editions.
5. Click a multi-volume edition card → `/edition/[editionKey]`; the back link
   returns to `/series/one-piece`.
6. Click a single-volume/standalone card → `/item/[slug]`; back returns to the
   series page.
7. `/series/does-not-exist` → 404.
8. `npm run build` succeeds (SSG over all `series_key`s).

---

## Docs to update when this lands

- **CLAUDE.md file map** — add `app/series/[seriesKey]/`, `components/series/`, and
  the new `lib/data.ts` functions; add the route to the data-flow diagram.
- **BP-002** — already promoted in this batch (route table updated).
- **README.md** (docs/web-next) — already indexed (FRD-007, WO-008).
- Bump "Last updated" in CLAUDE.md with a one-paragraph summary.
