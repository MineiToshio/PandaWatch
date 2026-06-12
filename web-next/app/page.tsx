import { loadClusters, buildFacets, groupByEdition, seriesFromClusters, aliasSearchIndex } from '@/lib/data'
import { parseFilterParams, filterClusters, sortClusters, paginate } from '@/lib/filters'
import { CatalogControls } from '@/components/catalog/CatalogControls'
import { CatalogGrid } from '@/components/catalog/CatalogGrid'
import { Pagination } from '@/components/catalog/Pagination'
import { SeriesHighlights } from '@/components/series/SeriesHighlights'
import type { Metadata } from 'next'

// Force dynamic rendering so searchParams is always fresh
export const dynamic = 'force-dynamic'

// FR-7: filtered/sorted/paginated views are noindex (avoid duplicate content +
// crawl-budget waste); the clean catalog `/` stays indexable and canonical.
// Title/description inherit the root layout defaults.
export async function generateMetadata({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[]>>
}): Promise<Metadata> {
  const sp = await searchParams
  const filtered = Object.keys(sp).length > 0
  return {
    alternates: { canonical: '/' },
    ...(filtered ? { robots: { index: false, follow: true } } : {}),
  }
}

export default async function CatalogPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[]>>
}) {
  const rawParams   = await searchParams
  const allClusters = loadClusters()
  const facets      = buildFacets(allClusters)
  const fp          = parseFilterParams(rawParams)
  const filtered    = filterClusters(allClusters, fp, aliasSearchIndex())
  const sorted      = sortClusters(filtered, fp.sort)
  const editions    = groupByEdition(sorted)
  const { items, pages, page } = paginate(editions, fp.page)

  const totalTomos    = filtered.length
  const totalEditions = editions.length
  const totalObras    = new Set(
    filtered.map(c => c.canonical.series_key).filter(Boolean)
  ).size

  // Series highlights derived from the filtered results — dynamic context:
  // no filter → global top 12; searching "demon slayer" → Demon Slayer card.
  const highlightSeries = seriesFromClusters(filtered)

  // Recortar los facets a lo que la UI muestra ANTES de serializarlos al
  // client component (los ~400 publishers completos viajaban en el payload
  // RSC para renderizar 12).
  const uiFacets = {
    ...facets,
    languages: facets.languages.slice(0, 8),
    publishers: facets.publishers.slice(0, 12),
  }

  return (
    <CatalogControls
      facets={uiFacets}
      current={fp}
      sort={fp.sort}
      page={page}
      pages={pages}
      totalTomos={totalTomos}
      totalEditions={totalEditions}
      totalObras={totalObras}
    >
      <SeriesHighlights series={highlightSeries} />
      <CatalogGrid clusters={items} eagerCovers={4} />
      {pages > 1 && <Pagination total={pages} current={page} />}
    </CatalogControls>
  )
}
