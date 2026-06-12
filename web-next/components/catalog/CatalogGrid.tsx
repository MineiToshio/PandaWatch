import type { Cluster } from '@/lib/types'
import { EditionCard } from './EditionCard'
import { EmptyState } from './EmptyState'

type CatalogGridProps = {
  clusters: Cluster[]
  /** Cuántas portadas above-the-fold cargan eager (LCP). 0 = todas lazy. */
  eagerCovers?: number
}

export function CatalogGrid({ clusters, eagerCovers = 0 }: CatalogGridProps) {
  if (clusters.length === 0) {
    return <EmptyState />
  }

  return (
    <div
      style={{ padding: '16px 16px 40px' }}
      className="catalog-grid"
    >
      <div className="catalog-grid-inner">
        {clusters.map((cluster, i) => (
          <EditionCard key={cluster.clusterKey} cluster={cluster} priority={i < eagerCovers} />
        ))}
      </div>
    </div>
  )
}

export default CatalogGrid
