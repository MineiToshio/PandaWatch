import { loadClusters, buildFacets, groupByEdition } from '@/lib/data'
import { parseFilterParams, filterClusters, sortClusters, paginate } from '@/lib/filters'
import { CatalogControls } from '@/components/catalog/CatalogControls'
import { CatalogGrid } from '@/components/catalog/CatalogGrid'
import { Pagination } from '@/components/catalog/Pagination'

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

  return (
    <CatalogControls
      facets={facets}
      current={fp}
      total={total}
      sort={fp.sort}
      page={page}
      pages={pages}
    >
      <CatalogGrid clusters={items} />
      {pages > 1 && <Pagination total={pages} current={page} />}
    </CatalogControls>
  )
}
