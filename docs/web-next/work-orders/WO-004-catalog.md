# WO-004: Catalog Page

**Phase:** 2  
**Effort:** L  
**Status:** Complete  
**Related:** [FRD-003](../FRD-003-catalog.md), [BP-004](../blueprints/BP-004-component-hierarchy.md)  
**Prerequisites:** WO-002 (design system), WO-003 (data layer)

---

## Objective

Implement the catalog page (`/`) — the main view of all manga special editions.
This is the highest-traffic page and the direct port of the Alpine.js catalog view.

---

## Tasks

### Task 1: Implement `app/page.tsx`

Server Component. Reads search params, loads and filters data, renders the page.

```tsx
import { loadClusters, buildFacets } from '@/lib/data'
import { filterClusters, sortClusters, paginate, parseFilterParams } from '@/lib/filters'
import { SidebarFilters } from '@/components/catalog/SidebarFilters'
import { CatalogGrid } from '@/components/catalog/CatalogGrid'
import { SortBar } from '@/components/catalog/SortBar'
import { Pagination } from '@/components/catalog/Pagination'

export default async function CatalogPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[]>>
}) {
  const params = await searchParams
  const allClusters = loadClusters()
  const facets = buildFacets(allClusters)
  
  const fp = parseFilterParams(params)
  const filtered = filterClusters(allClusters, fp)
  const sorted = sortClusters(filtered, fp.sort)
  const { items, total, pages, page } = paginate(sorted, fp.page || 1)

  return (
    <div className="flex min-h-screen">
      <SidebarFilters facets={facets} current={fp} />
      <div className="flex-1 flex flex-col">
        <SortBar total={total} sort={fp.sort} page={page} pages={pages} />
        <CatalogGrid clusters={items} />
        {pages > 1 && <Pagination total={pages} current={page} />}
      </div>
    </div>
  )
}

export const metadata = {
  title: 'PandaWatch 🐼 — Ediciones Especiales de Manga',
  description: 'Rastreador personal de ediciones especiales, variantes y cofres de manga.',
}
```

### Task 2: Implement `EditionCard`

File: `components/catalog/EditionCard.tsx`

Key logic:
- `href`: `/edition/${cluster.editionKey}` if editionKey exists, else `/item/${cluster.slug}`
- `data-leaves` attribute for stack CSS: `1` if volumeCount ≤ 1, `2` if 2–4, `3` if 5+
- Cover image via `CoverImage` component
- Signal chips: show top 3, rest as `+N más`

```tsx
import Link from 'next/link'
import Image from 'next/image'
import { cn } from '@/lib/styles'
import { SignalChip } from '@/components/modules/SignalChip'
import { ScoreBadge } from '@/components/modules/ScoreBadge'
import { CountryFlag } from '@/components/modules/CountryFlag'
import type { Cluster } from '@/lib/types'

export function EditionCard({ cluster, priority }: { cluster: Cluster; priority?: boolean }) {
  const { canonical, editionKey, slug, volumeCount, signalTypes } = cluster
  const href = editionKey ? `/edition/${editionKey}` : `/item/${slug}`
  const leaves = volumeCount >= 5 ? 3 : volumeCount >= 2 ? 2 : 1
  const topSignals = signalTypes.slice(0, 3)
  const extraSignals = signalTypes.length - topSignals.length

  return (
    <Link href={href} className="group">
      <article
        className="edition-card rounded-lg overflow-hidden bg-[var(--surface-1)] border border-[var(--border)]
                   transition-all duration-200 hover:-translate-y-1 hover:shadow-elevation-2"
        data-leaves={leaves}
      >
        {/* Cover */}
        <div className="aspect-[2/3] relative bg-[var(--surface-2)]">
          <CoverImage
            imageLocal={canonical.image_local}
            imageUrl={canonical.image_url}
            alt={canonical.title}
            fill
            sizes="(max-width: 480px) 50vw, (max-width: 768px) 33vw, (max-width: 1024px) 25vw, 20vw"
            priority={priority}
          />
          <div className="absolute top-2 right-2">
            <ScoreBadge score={canonical.score} />
          </div>
          {volumeCount > 1 && (
            <div className="absolute bottom-2 left-2 bg-black/70 text-white text-xs px-2 py-0.5 rounded">
              {volumeCount} tomos
            </div>
          )}
        </div>
        
        {/* Info */}
        <div className="p-3 space-y-1.5">
          <p className="text-[var(--text-primary)] font-medium text-sm line-clamp-2 leading-snug">
            {cluster.seriesDisplay || canonical.title}
          </p>
          {cluster.editionDisplay && (
            <p className="text-[var(--text-secondary)] text-xs line-clamp-1">
              {cluster.editionDisplay}
            </p>
          )}
          <div className="flex items-center gap-1 text-xs text-[var(--text-tertiary)]">
            <CountryFlag country={canonical.country} />
            {canonical.publisher && (
              <span className="truncate">{canonical.publisher}</span>
            )}
          </div>
          {topSignals.length > 0 && (
            <div className="flex flex-wrap gap-1 pt-0.5">
              {topSignals.map(s => <SignalChip key={s} signal={s} size="sm" />)}
              {extraSignals > 0 && (
                <span className="text-xs text-[var(--text-tertiary)]">+{extraSignals}</span>
              )}
            </div>
          )}
        </div>
      </article>
    </Link>
  )
}
```

### Task 3: Implement `CatalogGrid`

File: `components/catalog/CatalogGrid.tsx`

Server Component. Renders the responsive grid with `EditionCard` children.
First 10 cards get `priority={true}` for LCP optimization.

```tsx
export function CatalogGrid({ clusters }: { clusters: Cluster[] }) {
  if (!clusters.length) return <EmptyState />
  
  return (
    <ul
      role="list"
      className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4 p-4"
    >
      {clusters.map((cluster, i) => (
        <li key={cluster.clusterKey}>
          <EditionCard cluster={cluster} priority={i < 10} />
        </li>
      ))}
    </ul>
  )
}
```

### Task 4: Implement `SidebarFilters` (Client Component)

File: `components/catalog/SidebarFilters.tsx`

This is the most complex component. Key behaviors:
- All filter changes call `router.replace('/?'+newParams, { scroll: false })`
- Debounce search input 300ms before updating URL
- On mobile: renders as a drawer (controlled by `useState`)
- Active filter count badge on the "Filtros" button (mobile)

Subcomponents:
- `FilterSection` — collapsible section with title
- `CheckboxList` — list of options with checkboxes and counts
- `SignalTypeFilterChips` — row of Chip components, click to toggle
- `ScoreRangeSlider` — range input with label
- `FilterToggle` — labeled toggle switch
- `ActiveFilters` — dismissible tags for active filters + "Limpiar" button

### Task 5: Implement `SortBar`

File: `components/catalog/SortBar.tsx`

Shows "N ediciones" count and a sort select.
The select calls `router.replace` on change.

```tsx
'use client'
export function SortBar({ total, sort, page, pages }) {
  const router = useRouter()
  const searchParams = useSearchParams()
  
  const onSortChange = (newSort: string) => {
    const params = new URLSearchParams(searchParams.toString())
    params.set('sort', newSort)
    params.delete('page')  // reset to page 1 on sort change
    router.replace(`/?${params}`, { scroll: false })
  }
  
  return (
    <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border)]">
      <span className="text-sm text-[var(--text-secondary)]">
        {total.toLocaleString('es')} ediciones
        {pages > 1 && ` · Página ${page} de ${pages}`}
      </span>
      <select value={sort} onChange={e => onSortChange(e.target.value)}>
        <option value="score_desc">Mejor puntuación</option>
        <option value="score_asc">Menor puntuación</option>
        <option value="date_desc">Más recientes</option>
        <option value="date_asc">Más antiguos</option>
        <option value="title_asc">Título A→Z</option>
        <option value="title_desc">Título Z→A</option>
      </select>
    </div>
  )
}
```

### Task 6: Implement `Pagination`

File: `components/catalog/Pagination.tsx`

Client Component. Shows page window: `< 1 2 ... 5 [6] 7 ... 14 >`.

```tsx
'use client'
export function Pagination({ total, current }: { total: number; current: number }) {
  const router = useRouter()
  const searchParams = useSearchParams()
  
  const goToPage = (page: number) => {
    const params = new URLSearchParams(searchParams.toString())
    if (page === 1) params.delete('page')
    else params.set('page', String(page))
    router.replace(`/?${params}`, { scroll: true })
  }
  
  const pages = buildPageWindow(current, total)  // [1, '...', 5, 6, 7, '...', 14]
  
  return (
    <nav className="flex justify-center gap-1 py-6">
      <button onClick={() => goToPage(current - 1)} disabled={current === 1}>←</button>
      {pages.map((p, i) =>
        p === '...' ? (
          <span key={i}>…</span>
        ) : (
          <button
            key={p}
            onClick={() => goToPage(Number(p))}
            className={cn(p === current && 'bg-[var(--accent)] text-white')}
          >
            {p}
          </button>
        )
      )}
      <button onClick={() => goToPage(current + 1)} disabled={current === total}>→</button>
    </nav>
  )
}
```

### Task 7: Add stack CSS to `globals.css`

```css
/* Edition card stack effect */
.edition-card { position: relative; }

.edition-card[data-leaves="2"]::before,
.edition-card[data-leaves="3"]::before {
  content: '';
  position: absolute;
  inset: 0;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: inherit;
  transform: translate(5px, 5px);
  z-index: -1;
}

.edition-card[data-leaves="3"]::after {
  content: '';
  position: absolute;
  inset: 0;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: inherit;
  transform: translate(10px, 10px);
  z-index: -2;
}
```

### Task 8: Implement `CoverImage` module component

File: `components/modules/CoverImage.tsx`

Handles the 3-fallback chain:
1. `/images/{image_local}` (local mirror via symlink)
2. `image_url` (remote)
3. 📚 emoji placeholder

```tsx
'use client'
import Image from 'next/image'
import { useState } from 'react'

export function CoverImage({ imageLocal, imageUrl, alt, ...props }) {
  const [src, setSrc] = useState(
    imageLocal ? `/images/${imageLocal}` : imageUrl || null
  )
  
  if (!src) return <PlaceholderCover />
  
  return (
    <Image
      src={src}
      alt={alt}
      onError={() => {
        if (src.startsWith('/images/') && imageUrl) setSrc(imageUrl)
        else setSrc(null)
      }}
      {...props}
    />
  )
}
```

Note: `CoverImage` is a Client Component because of `useState` for error fallback.
However, the `onError` handler is rarely triggered (local mirror has 99.8% coverage).

### Task 9: Add `EmptyState` component

File: `components/catalog/EmptyState.tsx`

Shows when filters return 0 results:
- "No encontramos ediciones con estos filtros."
- Link to clear all filters

---

## Files Created/Modified

- `web-next/app/page.tsx`
- `web-next/components/catalog/EditionCard.tsx`
- `web-next/components/catalog/CatalogGrid.tsx`
- `web-next/components/catalog/SidebarFilters.tsx`
- `web-next/components/catalog/SortBar.tsx`
- `web-next/components/catalog/Pagination.tsx`
- `web-next/components/catalog/EmptyState.tsx`
- `web-next/components/modules/CoverImage.tsx`
- `web-next/app/globals.css` (add stack CSS)

---

## Acceptance Criteria

- [x] Catalog loads and displays all items from items.jsonl
- [x] Stack CSS shows 1/2/3 leaves correctly
- [x] Cover images load from `/images/` symlink (3-fallback chain: local → remote → BookOpen icon)
- [x] Search for "berserk" filters in real-time (debounced 300ms, URL updated)
- [x] Country filter with JP selected shows only Japanese items
- [x] Signal type chip filter with AND logic works
- [x] Sort dropdown changes order and updates URL
- [x] Pagination shows correct page window; navigating changes URL `?page=N`
- [x] URL with `?q=berserk&country=JP` loads pre-filtered on first render
- [x] "Limpiar todo" navigates to `/` and shows all items
- [x] Mobile: filters accessible via slide-over drawer

## Implementation Notes (2026-05-27)

**Architecture delta vs. WO-004 spec:**
- Added `CatalogControls.tsx` (Client Component) to manage `drawerOpen` state shared between `SortBar` (toggle button) and `SidebarFilters` (drawer content). This solves the sibling state problem without lifting state to a Server Component.
- `page.tsx` passes `CatalogGrid` + `Pagination` as `children` to `CatalogControls` (Server/Client slot composition pattern).
- `export const dynamic = 'force-dynamic'` on `page.tsx` avoids the `useSearchParams`+Suspense requirement — the page is dynamic because it `await`s `searchParams`.
- `CoverImage`: uses Next.js `<Image>` for local paths, plain `<img>` for remote fallback (avoiding `remotePatterns` config across ~76 scrape domains).
- `CountryFlag`: extended to include Spanish country names (`Japón`, `Francia`, `Alemania`, `Italia`, `Brasil`, `Tailandia`, `Taiwán`, `Estados Unidos`) matching how `items.jsonl` stores country values.
- No dark mode, no emoji in UI (Lucide icons throughout, CountryFlag flag emoji excepted per spec).

**Post-implementation fix (2026-05-27) — edition grouping:**
- Added `groupByEdition(clusters: Cluster[]): Cluster[]` to `lib/data.ts` (see FR-3b in FRD-001). Collapses all clusters with the same `edition_key` into one representative catalog card. Without this, Berserk Deluxe Vol.1 through Vol.15 each rendered as a separate card — the intended UX is one "Berserk Deluxe Edition" card with a 3-leaf stack and `volumeCount=15`.
- `app/page.tsx` updated: `sortClusters(filtered) → groupByEdition(sorted) → paginate(editions)`. The `total` count and pagination now reflect edition groups, not raw volumes.
- `EditionCard` href priority fixed: was checking `slug` first (every cluster has a slug → everything went to `/item/…`). Now checks `editionKey` first per FRD-003 spec: editions → `/edition/[editionKey]`, standalone items → `/item/[slug]`.

**Post-implementation fix (2026-05-27) — stacked card hover bug (inner wrapper pattern):**

Root cause: the original `EditionCard` had `overflow: hidden` + `border-radius` on the outer `<Link>` element (`edition-card`). CSS `overflow: hidden` together with a border-radius creates a stacking context. On hover, `transform: translateY(-3px)` also creates a stacking context. Inside a stacking context, the `::before`/`::after` pseudo-elements with `z-index: -1/-2` paint *above* the element's own `background` but *below* its child elements. Since the info section's text divs have no explicit background (transparent), the brownish paper layers bled through gaps between text elements — visually a partial brownish stripe at the bottom of cards.

Fix — **inner wrapper pattern**:
1. Outer `<Link className="edition-card">`: removed `overflow: hidden`, `background`, `border`, `borderRadius` from inline styles. Kept only layout/navigation properties. Added `z-index: 0` in CSS (creates stacking context at rest so paper layers are visible from the start, not just on hover). Added `border-radius: var(--radius-md)` so pseudo-elements can `border-radius: inherit`.
2. Added `<div className="edition-card-inner">` wrapping all card content (cover + info). This inner div has `overflow: hidden; background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-md)`. Its solid white background covers the pseudo-elements within the card boundary, preventing any bleed-through. The pseudo-elements' portions that extend *outside* the inner div (and outside the outer Link) peek out as stacked paper layers.
3. Hover CSS moved from `CatalogGrid.tsx` inline `<style>` to `globals.css`, alongside the stack pseudo-element rules.

Stack pseudo-element CSS (in `globals.css`):
```css
.edition-card {
  position: relative; z-index: 0;  /* stacking context at rest */
  border-radius: var(--radius-md); display: block; text-decoration: none;
  color: inherit; transition: transform 0.15s var(--ease-out-quart);
}
.edition-card:hover { transform: translateY(-3px); }
.edition-card:hover .edition-card-inner { box-shadow: var(--shadow-md); }
.edition-card-inner {
  border-radius: var(--radius-md); background: var(--color-surface);
  border: 1px solid var(--color-border); overflow: hidden;
  transition: box-shadow 0.15s var(--ease-out-quart);
}
/* Stack layer 1 (data-leaves 2 or 3) */
.edition-card[data-leaves="2"]::before, .edition-card[data-leaves="3"]::before {
  content:''; position:absolute; inset:0; background:#E8E2D6;
  border:1px solid #D1C9BB; border-radius:inherit;
  transform:translate(5px,6px); z-index:-1;
}
/* Stack layer 2 (data-leaves 3 only) */
.edition-card[data-leaves="3"]::after {
  content:''; position:absolute; inset:0; background:#DDD6C9;
  border:1px solid #C5BDB0; border-radius:inherit;
  transform:translate(10px,12px); z-index:-2;
}
```

`data-leaves` values: `1` = single volume (no stack), `2` = 2–4 volumes (1 layer), `3` = 5+ volumes (2 layers). Colors are warm brownish paper tones matching the PandaWatch warm background palette.

**Post-implementation fix (2026-05-27) — CSS grid overflow (`1fr` vs `minmax(0, 1fr)`):**

Root cause: `repeat(N, 1fr)` is shorthand for `repeat(N, minmax(auto, 1fr))`. The `auto` minimum means each column can never be narrower than the minimum content size of its items. `EditionCard` has `whiteSpace: 'nowrap'` on the series display paragraph, which forces a minimum content width of ~258px per card — wider than the available fraction. The grid expanded columns past the viewport causing ~124px horizontal overflow.

Fix:
1. Changed all `repeat(N, 1fr)` → `repeat(N, minmax(0, 1fr))` in `.catalog-grid-inner` (in `globals.css`). The explicit `0` minimum allows columns to shrink to their true fractional share regardless of child content.
2. Added `min-width: 0` to `.edition-card` CSS rule. Grid items default to `min-width: auto`, which prevents them from shrinking below content size even when the column constraint says otherwise. `min-width: 0` opts the item out of that floor.
3. Moved all responsive `<style>` tags that were inline in `CatalogGrid.tsx`, `SortBar.tsx`, and `SidebarFilters.tsx` into `globals.css`. React 19's style hoisting/deduplication can cause inline `<style>` tags in components to behave unpredictably. All grid and visibility media queries now live in one place.

Responsive breakpoints (as implemented, from `globals.css`):
```css
.catalog-grid-inner { grid-template-columns: repeat(2, minmax(0, 1fr)); }        /* default: 2 cols */
@media (min-width: 480px)  { .catalog-grid-inner { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (min-width: 1024px) { .catalog-grid-inner { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
@media (min-width: 1280px) { .catalog-grid-inner { grid-template-columns: repeat(5, minmax(0, 1fr)); } }
```

Responsive sidebar/button visibility (also in `globals.css`):
```css
@media (max-width: 1023px)  { .sidebar-desktop   { display: none !important; } }
@media (min-width: 1024px)  { .sidebar-mobile-overlay, .sidebar-close-btn, .sort-filter-btn { display: none !important; } }
```
