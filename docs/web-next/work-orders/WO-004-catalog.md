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
