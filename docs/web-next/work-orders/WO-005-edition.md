# WO-005: Edition Detail Page

**Phase:** 3  
**Effort:** M  
**Status:** Pending  
**Related:** [FRD-004](../FRD-004-edition-detail.md), [BP-002](../blueprints/BP-002-url-routing.md)  
**Prerequisites:** WO-004 (catalog page — EditionCard and core components done)

---

## Objective

Implement the edition detail page (`/edition/[editionKey]`). Shows all volumes of
one edition in a grid with full static generation.

---

## Tasks

### Task 1: Implement `app/edition/[editionKey]/page.tsx`

```tsx
import { notFound } from 'next/navigation'
import { loadEditionClusters, allEditionKeys } from '@/lib/data'
import { EditionHeader } from '@/components/edition/EditionHeader'
import { VolumeGrid } from '@/components/edition/VolumeGrid'
import { BackLink } from '@/components/modules/BackLink'

type Props = {
  params: Promise<{ editionKey: string }>
  searchParams: Promise<{ from?: string }>
}

export default async function EditionPage({ params, searchParams }: Props) {
  const { editionKey } = await params
  const { from } = await searchParams
  const clusters = loadEditionClusters(editionKey)
  
  if (!clusters.length) notFound()
  
  const firstCluster = clusters[0]
  
  return (
    <main className="max-w-7xl mx-auto px-4 py-6">
      <BackLink href={from === 'catalog' ? '/' : '/'} label="← Catálogo" />
      <EditionHeader cluster={firstCluster} totalVolumes={clusters.length} />
      <VolumeGrid clusters={clusters} editionKey={editionKey} />
    </main>
  )
}

export async function generateStaticParams() {
  return allEditionKeys().map(editionKey => ({ editionKey }))
}

export async function generateMetadata({ params }: Props) {
  const { editionKey } = await params
  const clusters = loadEditionClusters(editionKey)
  if (!clusters.length) return {}
  
  const { canonical } = clusters[0]
  return {
    title: `${canonical.edition_display || canonical.series_display} — PandaWatch`,
    description: `${clusters.length} tomos · ${canonical.publisher} · ${canonical.country}`,
    openGraph: {
      images: canonical.image_url ? [canonical.image_url] : [],
    },
  }
}
```

### Task 2: Implement `EditionHeader`

File: `components/edition/EditionHeader.tsx`

```tsx
import { Heading } from '@/components/core/Heading'
import { Typography } from '@/components/core/Typography'
import { SignalChip } from '@/components/modules/SignalChip'
import { ScoreBadge } from '@/components/modules/ScoreBadge'
import { CountryFlag } from '@/components/modules/CountryFlag'
import type { Cluster } from '@/lib/types'

export function EditionHeader({
  cluster,
  totalVolumes,
}: {
  cluster: Cluster
  totalVolumes: number
}) {
  const { canonical, signalTypes } = cluster
  
  return (
    <header className="mb-8 pb-6 border-b border-[var(--border)]">
      <div className="flex items-start gap-4">
        {/* Series cover (small) */}
        <div className="w-16 aspect-[2/3] rounded overflow-hidden flex-shrink-0">
          <CoverImage
            imageLocal={canonical.image_local}
            imageUrl={canonical.image_url}
            alt={canonical.title}
            width={64}
            height={96}
          />
        </div>
        
        <div className="flex-1">
          <Typography variant="eyebrow" className="text-[var(--accent)]">
            {canonical.country && <CountryFlag country={canonical.country} />}
            {canonical.publisher}
          </Typography>
          
          <Heading as="h1" size="h2" className="mt-1">
            {cluster.seriesDisplay}
          </Heading>
          
          {cluster.editionDisplay && (
            <Heading as="h2" size="h3" className="text-[var(--text-secondary)] mt-1">
              {cluster.editionDisplay}
            </Heading>
          )}
          
          <div className="flex items-center gap-3 mt-3">
            <Typography variant="body-sm" className="text-[var(--text-tertiary)]">
              {totalVolumes} {totalVolumes === 1 ? 'tomo' : 'tomos'}
            </Typography>
            <ScoreBadge score={canonical.score} />
          </div>
          
          {signalTypes.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-3">
              {signalTypes.map(s => <SignalChip key={s} signal={s} />)}
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
```

### Task 3: Implement `VolumeGrid`

File: `components/edition/VolumeGrid.tsx`

Renders `ItemCard` for each cluster in the edition:

```tsx
import { ItemCard } from '@/components/modules/ItemCard'
import type { Cluster } from '@/lib/types'

export function VolumeGrid({
  clusters,
  editionKey,
}: {
  clusters: Cluster[]
  editionKey: string
}) {
  return (
    <ul
      role="list"
      className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4"
    >
      {clusters.map(cluster => (
        <li key={cluster.clusterKey}>
          <ItemCard cluster={cluster} from={`edition:${editionKey}`} />
        </li>
      ))}
    </ul>
  )
}
```

### Task 4: Implement `ItemCard`

File: `components/modules/ItemCard.tsx`

Used both in the edition page and potentially in search results.
Navigates to `/item/[slug]?from={from}`.

```tsx
import Link from 'next/link'
import type { Cluster } from '@/lib/types'

export function ItemCard({
  cluster,
  from,
}: {
  cluster: Cluster
  from?: string
}) {
  const { canonical, slug } = cluster
  const href = slug
    ? `/item/${slug}${from ? `?from=${from}` : ''}`
    : '#'  // fallback if slug missing (shouldn't happen post-standardization)
  
  return (
    <Link href={href} className="group">
      <article className="rounded-lg overflow-hidden border border-[var(--border)]
                         bg-[var(--surface-1)] hover:-translate-y-1 transition-transform">
        {/* Volume badge */}
        <div className="aspect-[2/3] relative bg-[var(--surface-2)]">
          <CoverImage
            imageLocal={canonical.image_local}
            imageUrl={canonical.image_url}
            alt={canonical.title}
            fill
            sizes="(max-width: 768px) 33vw, 20vw"
          />
          {canonical.volume && (
            <div className="absolute top-2 left-2 bg-black/80 text-white text-xs
                           font-bold px-1.5 py-0.5 rounded">
              Vol. {canonical.volume}
            </div>
          )}
          <div className="absolute top-2 right-2">
            <ScoreBadge score={canonical.score} />
          </div>
        </div>
        
        <div className="p-2.5 space-y-1">
          <p className="text-xs font-medium text-[var(--text-primary)] line-clamp-2">
            {canonical.title}
          </p>
          {canonical.price && (
            <p className="text-xs text-[var(--accent)] font-semibold">{canonical.price}</p>
          )}
          {canonical.release_date && (
            <p className="text-xs text-[var(--text-tertiary)]">
              {formatDate(canonical.release_date)}
            </p>
          )}
          <div className="flex flex-wrap gap-1">
            {cluster.signalTypes.slice(0, 2).map(s => (
              <SignalChip key={s} signal={s} size="sm" />
            ))}
          </div>
        </div>
      </article>
    </Link>
  )
}
```

### Task 5: Implement `BackLink`

File: `components/modules/BackLink.tsx`

Simple server component:
```tsx
import Link from 'next/link'

export function BackLink({ href, label }: { href: string; label: string }) {
  return (
    <Link
      href={href}
      className="inline-flex items-center gap-1 text-sm text-[var(--text-secondary)]
                 hover:text-[var(--accent)] mb-6"
    >
      {label}
    </Link>
  )
}
```

---

## Files Created/Modified

- `web-next/app/edition/[editionKey]/page.tsx`
- `web-next/components/edition/EditionHeader.tsx`
- `web-next/components/edition/VolumeGrid.tsx`
- `web-next/components/modules/ItemCard.tsx`
- `web-next/components/modules/BackLink.tsx`

---

## Acceptance Criteria

- [ ] `/edition/berserk-darkhorse-deluxe` loads and shows all Berserk Deluxe volumes
- [ ] Volumes sorted by volume number ascending; no-volume items at end
- [ ] Edition header shows series name, edition name, publisher, country, signal chips
- [ ] `generateStaticParams()` includes routes for all edition_keys in corpus
- [ ] Non-existent edition key returns 404
- [ ] Page `<title>` set correctly
- [ ] `← Catálogo` link navigates to `/`
- [ ] Each ItemCard links to `/item/[slug]?from=edition:{editionKey}`
