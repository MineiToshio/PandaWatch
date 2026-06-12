# WO-006: Item Detail Page

**Phase:** 3  
**Effort:** L  
**Status:** Done  
**Related:** [FRD-005](../FRD-005-item-detail.md), [BP-002](../blueprints/BP-002-url-routing.md), [BP-004](../blueprints/BP-004-component-hierarchy.md)  
**Prerequisites:** WO-004 (catalog), WO-005 (edition — ItemCard and BackLink done)

---

## Objective

Implement the item detail page (`/item/[slug]`). The deepest view — shows all
information about a single item including the image carousel, metadata, extras,
and multi-source table.

---

## Tasks

### Task 1: Implement `app/item/[slug]/page.tsx`

```tsx
import { notFound } from 'next/navigation'
import { clusterBySlug, allSlugs } from '@/lib/data'
import { ItemHero } from '@/components/item/ItemHero'
import { MetaTable } from '@/components/item/MetaTable'
import { ExtrasSection } from '@/components/item/ExtrasSection'
import { SourcesList } from '@/components/item/SourcesList'
import { BackLink } from '@/components/modules/BackLink'

type Props = {
  params: Promise<{ slug: string }>
  searchParams: Promise<{ from?: string }>
}

export default async function ItemPage({ params, searchParams }: Props) {
  const { slug } = await params
  const { from } = await searchParams
  const cluster = clusterBySlug(slug)
  
  if (!cluster) notFound()
  
  const { canonical, items } = cluster
  
  // Parse back navigation
  const backHref = from?.startsWith('edition:')
    ? `/edition/${from.slice(8)}`
    : '/'
  const backLabel = from?.startsWith('edition:')
    ? `← ${cluster.editionDisplay || cluster.seriesDisplay || 'Edición'}`
    : '← Catálogo'
  
  return (
    <main className="max-w-5xl mx-auto px-4 py-6">
      <BackLink href={backHref} label={backLabel} />
      
      <article>
        <ItemHero cluster={cluster} />
        
        <div className="mt-8 grid grid-cols-1 md:grid-cols-2 gap-8">
          <MetaTable item={canonical} />
          {(canonical.extras?.length ?? 0) > 0 && (
            <ExtrasSection extras={canonical.extras!} />
          )}
        </div>
        
        {items.length > 1 && (
          <div className="mt-8">
            <SourcesList items={items} />
          </div>
        )}
      </article>
    </main>
  )
}

export async function generateStaticParams() {
  return allSlugs().map(slug => ({ slug }))
}

export async function generateMetadata({ params }: Props) {
  const { slug } = await params
  const cluster = clusterBySlug(slug)
  if (!cluster) return {}
  
  const { canonical } = cluster
  return {
    title: `${canonical.title} — PandaWatch`,
    description: buildItemDescription(canonical),
    openGraph: {
      type: 'book',
      images: canonical.image_url ? [canonical.image_url] : [],
      ...(canonical.isbn && { 'og:isbn': canonical.isbn }),
    },
  }
}

function buildItemDescription(item: Item): string {
  const parts = [
    item.edition_display,
    item.publisher,
    item.country,
    item.release_date && `Lanzamiento: ${formatDate(item.release_date)}`,
  ].filter(Boolean)
  return parts.join(' · ')
}
```

### Task 2: Implement `ItemHero`

File: `components/item/ItemHero.tsx`

Two-column layout (carousel + metadata):

```tsx
import { ImageCarousel } from '@/components/item/ImageCarousel'
import { Heading } from '@/components/core/Heading'
import { Typography } from '@/components/core/Typography'
import { SignalChip } from '@/components/modules/SignalChip'
import { ScoreBadge } from '@/components/modules/ScoreBadge'
import { CountryFlag } from '@/components/modules/CountryFlag'
import type { Cluster } from '@/lib/types'

export function ItemHero({ cluster }: { cluster: Cluster }) {
  const { canonical, signalTypes } = cluster
  
  // Build images array for carousel
  const images = canonical.images?.length
    ? canonical.images
    : canonical.image_url || canonical.image_local
      ? [{ url: canonical.image_url || '', local: canonical.image_local, kind: 'cover' as const }]
      : []
  
  return (
    <div className="flex flex-col md:flex-row gap-8">
      {/* Carousel */}
      <div className="md:w-2/5 flex-shrink-0">
        <ImageCarousel images={images} alt={canonical.title} />
      </div>
      
      {/* Metadata */}
      <div className="flex-1 space-y-4">
        {/* Breadcrumb */}
        {canonical.series_display && canonical.edition_display && (
          <Typography variant="eyebrow" className="text-[var(--text-tertiary)]">
            {canonical.series_display}
          </Typography>
        )}
        
        {/* Title */}
        <Heading as="h1" size="h2">{canonical.title}</Heading>
        
        {/* Original title */}
        {canonical.title_original && canonical.title_original !== canonical.title && (
          <Typography variant="body-sm" className="text-[var(--text-tertiary)] italic">
            原題: {canonical.title_original}
          </Typography>
        )}
        
        {/* Publisher + country */}
        <div className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
          {canonical.country && <CountryFlag country={canonical.country} showLabel />}
          {canonical.publisher && <span>· {canonical.publisher}</span>}
          {canonical.language && <span>· {canonical.language}</span>}
        </div>
        
        {/* Score + signals */}
        <div className="flex items-center gap-2 flex-wrap">
          <ScoreBadge score={canonical.score} showLabel />
          {signalTypes.map(s => <SignalChip key={s} signal={s} />)}
        </div>
        
        {/* Key purchase info */}
        <div className="space-y-1 pt-2">
          {canonical.release_date && (
            <Typography variant="body-sm">
              Lanzamiento: {formatDate(canonical.release_date)}
            </Typography>
          )}
          {canonical.isbn && (
            <Typography variant="caption" className="text-[var(--text-tertiary)]">
              ISBN: {formatISBN(canonical.isbn)}
            </Typography>
          )}
        </div>
      </div>
    </div>
  )
}
```

### Task 3: Implement `ImageCarousel` (Client Component)

File: `components/item/ImageCarousel.tsx`

```tsx
'use client'
import { useState, useEffect } from 'react'
import Image from 'next/image'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import type { ItemImage } from '@/lib/types'

const KIND_LABELS: Record<string, string> = {
  cover: 'Portada',
  gallery: 'Galería',
  extra: 'Extra',
  variant_cover: 'Portada Alternativa',
  back_cover: 'Contraportada',
}

export function ImageCarousel({ images, alt }: { images: ItemImage[]; alt: string }) {
  const [idx, setIdx] = useState(0)
  const [imgSrc, setImgSrc] = useState<string | null>(null)
  
  const current = images[idx]
  
  useEffect(() => {
    if (!current) return
    const src = current.local ? `/images/${current.local}` : current.url || null
    setImgSrc(src)
  }, [idx, current])
  
  const prev = () => setIdx(i => (i - 1 + images.length) % images.length)
  const next = () => setIdx(i => (i + 1) % images.length)
  
  // Keyboard navigation
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft') prev()
      if (e.key === 'ArrowRight') next()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])
  
  if (!images.length) return <PlaceholderCover className="w-full aspect-[2/3]" />
  
  return (
    <div className="space-y-2" role="region" aria-label="Galería de imágenes">
      {/* Main image */}
      <div className="aspect-[2/3] relative bg-[var(--surface-2)] rounded-lg overflow-hidden">
        {imgSrc ? (
          <Image
            src={imgSrc}
            alt={`${alt} — ${KIND_LABELS[current.kind] || current.kind}`}
            fill
            className="object-contain"
            onError={() => {
              if (imgSrc.startsWith('/images/') && current.url) setImgSrc(current.url)
              else setImgSrc(null)
            }}
          />
        ) : (
          <PlaceholderCover />
        )}
        
        {/* Kind badge */}
        <div className="absolute top-2 left-2 bg-black/70 text-white text-xs px-2 py-0.5 rounded">
          {KIND_LABELS[current.kind] || current.kind}
        </div>
        
        {/* Arrows */}
        {images.length > 1 && (
          <>
            <button
              onClick={prev}
              aria-label="Imagen anterior"
              className="absolute left-2 top-1/2 -translate-y-1/2 bg-black/50 hover:bg-black/70
                         text-white rounded-full p-1.5 transition-colors"
            >
              <ChevronLeft size={20} />
            </button>
            <button
              onClick={next}
              aria-label="Imagen siguiente"
              className="absolute right-2 top-1/2 -translate-y-1/2 bg-black/50 hover:bg-black/70
                         text-white rounded-full p-1.5 transition-colors"
            >
              <ChevronRight size={20} />
            </button>
          </>
        )}
      </div>
      
      {/* Description */}
      {current.description && (
        <p className="text-xs text-center text-[var(--text-secondary)]">
          {current.description}
        </p>
      )}
      
      {/* Dots (max 8) */}
      {images.length > 1 && images.length <= 8 && (
        <div className="flex justify-center gap-1.5">
          {images.map((_, i) => (
            <button
              key={i}
              onClick={() => setIdx(i)}
              aria-label={`Imagen ${i + 1}`}
              aria-current={i === idx}
              className={cn(
                'w-1.5 h-1.5 rounded-full transition-colors',
                i === idx ? 'bg-[var(--accent)]' : 'bg-[var(--border)]'
              )}
            />
          ))}
        </div>
      )}
    </div>
  )
}
```

### Task 4: Implement `MetaTable`

File: `components/item/MetaTable.tsx`

```tsx
import type { Item } from '@/lib/types'

const PRODUCT_TYPE_LABELS: Record<string, string> = {
  manga: 'Manga',
  boxset: 'Cofre / Box Set',
  artbook: 'Artbook',
  fanbook: 'Fanbook',
  magazine: 'Revista',
  novel: 'Novela',
}

export function MetaTable({ item }: { item: Item }) {
  const rows = [
    { label: 'ISBN',            value: item.isbn && formatISBN(item.isbn) },
    { label: 'Lanzamiento',     value: item.release_date && formatDate(item.release_date) },
    { label: 'Autor',           value: item.author },
    { label: 'Editorial',       value: item.publisher },
    { label: 'País',            value: item.country },
    { label: 'Idioma',          value: item.language },
    { label: 'Tipo',            value: item.product_type && PRODUCT_TYPE_LABELS[item.product_type] },
    { label: 'Puntuación',      value: item.score, render: () => <ScoreBadge score={item.score} /> },
    { label: 'Detectado',       value: item.detected_at && formatDate(item.detected_at) },
    { label: 'Estandarizado',   value: item.standardized_at
                                         ? formatDate(item.standardized_at)
                                         : 'Pendiente' },
  ].filter(r => r.value)
  
  return (
    <section>
      <h2 className="text-sm font-semibold text-[var(--text-secondary)] uppercase tracking-wider mb-3">
        Datos del producto
      </h2>
      <dl className="space-y-2">
        {rows.map(({ label, value, render }) => (
          <div key={label} className="flex gap-2">
            <dt className="text-xs text-[var(--text-tertiary)] w-28 flex-shrink-0">{label}</dt>
            <dd className="text-sm text-[var(--text-primary)]">
              {render ? render() : String(value)}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  )
}
```

### Task 5: Implement `ExtrasSection`

File: `components/item/ExtrasSection.tsx`

```tsx
import type { ItemExtra } from '@/lib/types'

export function ExtrasSection({ extras }: { extras: ItemExtra[] }) {
  return (
    <section>
      <h2 className="text-sm font-semibold text-[var(--text-secondary)] uppercase tracking-wider mb-3">
        Incluye / Extras de primera edición
      </h2>
      <ul className="space-y-2">
        {extras.map((extra, i) => (
          <li key={i} className="flex items-start gap-2 text-sm">
            <span className="text-[var(--accent)] mt-0.5">🎁</span>
            <div>
              <span className="text-[var(--text-primary)]">{extra.description}</span>
              {extra.release_date && (
                <span className="text-xs text-[var(--text-tertiary)] ml-2">
                  {formatDate(extra.release_date)}
                </span>
              )}
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}
```

### Task 6: Implement `SourcesList`

File: `components/item/SourcesList.tsx`

```tsx
import type { Item } from '@/lib/types'
import { ExternalLink } from 'lucide-react'

export function SourcesList({ items }: { items: Item[] }) {
  return (
    <section>
      <h2 className="text-sm font-semibold text-[var(--text-secondary)] uppercase tracking-wider mb-3">
        Fuentes ({items.length})
      </h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-[var(--text-tertiary)] border-b border-[var(--border)]">
              <th className="text-left py-2 pr-4">Fuente</th>
              <th className="text-left py-2 pr-4">Fecha</th>
              <th className="text-left py-2">Stock</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, i) => (
              <tr key={i} className="border-b border-[var(--border)] last:border-0">
                <td className="py-2 pr-4">
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1 text-[var(--accent)] hover:underline"
                  >
                    {item.source || new URL(item.url).hostname}
                    <ExternalLink size={12} />
                  </a>
                </td>
                <td className="py-2 pr-4 text-[var(--text-secondary)]">
                  {item.release_date ? formatDate(item.release_date) : '—'}
                </td>
                <td className="py-2 text-[var(--text-secondary)]">
                  {item.stock_type || '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
```

---

## Files Created/Modified

- `web-next/app/item/[slug]/page.tsx`
- `web-next/components/item/ItemHero.tsx`
- `web-next/components/item/ImageCarousel.tsx`
- `web-next/components/item/MetaTable.tsx`
- `web-next/components/item/ExtrasSection.tsx`
- `web-next/components/item/SourcesList.tsx`

---

## Acceptance Criteria

- [x] `/item/kobato-norma-regular-6` loads with correct title, images, metadata
- [x] Image carousel shows all images in `images[]` array
- [x] Arrows and dots work; keyboard Left/Right works
- [x] Kind badge shows "Portada" / "Galería" / "Extra" on each image
- [x] Image fallback chain works: local → remote → placeholder
- [x] `title_original` shown in italic when different from `title`
- [x] Signal type chips with icons and correct labels
- [x] `ExtrasSection` renders when `extras[]` is non-empty (verified: Kobato 6 shows "Cofre para tomos 1 a 6")
- [x] `SourcesList` renders when cluster has > 1 source (verified: isbn-9784301004899 shows FUENTES (2))
- [x] `{editionDisplay}` back label appears when navigating from edition page
- [x] `Catálogo` back label appears when navigating from catalog
- [x] Non-existent slug returns 404
- [x] `generateStaticParams()` covers all slugs in corpus
- [x] No TypeScript errors (`npm run type-check` exits clean)

---

## Implementation Notes

### Delta from spec

1. **No Tailwind classes** — The spec used Tailwind utility classes (`className="max-w-5xl mx-auto..."`, `className="flex flex-col md:flex-row..."`). The project uses inline styles and `<style>` tags with `@media` queries (consistent with EditionHeader, VolumeGrid, CatalogGrid). All layout CSS was converted to inline styles and scoped `<style>` blocks.

2. **CSS variable corrections** — The spec referenced `var(--text-tertiary)`, `var(--text-secondary)`, `var(--surface-2)`, `var(--border)`, and `var(--accent)` which don't exist in the design system. Replaced with the correct tokens: `var(--color-text-tertiary)`, `var(--color-text-secondary)`, `var(--ink-100)`, `var(--color-border)`, and `var(--bamboo-500)` / `var(--vermillion-500)`.

3. **No `←` prefix on BackLink label** — The spec wrote `← ${editionDisplay}` and `← Catálogo`. BackLink already renders a `<ChevronLeft>` Lucide icon, so the arrow prefix was dropped.

4. **No emojis** — The spec used `🎁` in ExtrasSection. Replaced with the `<Gift>` Lucide icon (size 14, bamboo-500 color) per the "no emojis in UI" project rule.

5. **`lib/format.ts` created** — `formatDate` and `formatISBN` are shared across page.tsx, ItemHero, MetaTable, SourcesList, and ExtrasSection. Extracted to a dedicated utility module rather than duplicating or inlining.

6. **`lib/types.ts` extended** — Added `detected_at?: string` and `stock_type?: string` to `Item`. These are standard scraped fields referenced by MetaTable and SourcesList but were missing from the type definition.

7. **ImageCarousel fallback handling** — For local images, uses `next/image` `<Image>` with `fill` + `object-contain`. For remote images (fallback), uses a plain `<img>` tag to avoid needing `remotePatterns` config for ~76 scrape domains (same pattern as `CoverImage`). The `handleError` callback tries the remote URL first, then falls back to the `<BookOpen>` placeholder.

8. **MetaTable Row type** — The spec showed `value: string | number | boolean | null | undefined`. Removing `boolean` was necessary to avoid a TypeScript false-overlap error in the filter condition; the Estandarizado row always renders (value = formatted date or `"Pendiente"`) so it never hits the filter anyway.

9. **`generateMetadata` description** — The spec had a standalone `buildItemDescription` helper that imported `Item`. Inlined the logic directly into `generateMetadata` to avoid a type import that wasn't used elsewhere in the file.

10. **Responsive layout via `<style>` tag** — ItemHero uses the same `<style>` + `.item-hero` class pattern as VolumeGrid/CatalogGrid: single column on mobile, `280px 1fr` two-column grid at `≥640px`.
