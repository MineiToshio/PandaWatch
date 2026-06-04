import { loadClusters, buildFacets, groupByEdition, seriesFromClusters } from '@/lib/data'
import { parseFilterParams, filterClusters, sortClusters, paginate } from '@/lib/filters'
import { CatalogControls } from '@/components/catalog/CatalogControls'
import { CatalogGrid } from '@/components/catalog/CatalogGrid'
import { Pagination } from '@/components/catalog/Pagination'
import { SeriesHighlights } from '@/components/series/SeriesHighlights'

export const metadata = { title: 'PandaWatch' }

// Force dynamic rendering so searchParams is always fresh
export const dynamic = 'force-dynamic'

export default async function CatalogPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[]>>
}) {
  const rawParams   = await searchParams
  const allClusters = loadClusters()
  const facets      = buildFacets(allClusters)
  const fp          = parseFilterParams(rawParams)
  const filtered    = filterClusters(allClusters, fp)
  const sorted      = sortClusters(filtered, fp.sort)
  const editions    = groupByEdition(sorted)
  const { items, total, pages, page } = paginate(editions, fp.page)

  const totalTomos    = filtered.length
  const totalEditions = editions.length
  const totalObras    = new Set(
    filtered.map(c => c.canonical.series_key).filter(Boolean)
  ).size

  // Series highlights derived from the filtered results — dynamic context:
  // no filter → global top 12; searching "demon slayer" → Demon Slayer card.
  const highlightSeries = seriesFromClusters(filtered)

  // Build the catalog URL to pass as ?from= in detail-page links,
  // so BackLink can return to the exact same filtered/paginated state.
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(rawParams)) {
    if (Array.isArray(v)) v.forEach(val => qs.append(k, val))
    else qs.append(k, v)
  }
  const catalogFrom = qs.toString() ? `/?${qs.toString()}` : '/'

  return (
    <CatalogControls
      facets={facets}
      current={fp}
      total={total}
      sort={fp.sort}
      page={page}
      pages={pages}
      totalTomos={totalTomos}
      totalEditions={totalEditions}
      totalObras={totalObras}
    >
      <SeriesHighlights series={highlightSeries} />
      <CatalogGrid clusters={items} from={catalogFrom} />
      {pages > 1 && <Pagination total={pages} current={page} />}
    </CatalogControls>
  )
}
