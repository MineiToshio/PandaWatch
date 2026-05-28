import type { Cluster } from '@/lib/types'
import { EditionCard } from './EditionCard'
import { EmptyState } from './EmptyState'

type CatalogGridProps = {
  clusters: Cluster[]
}

export function CatalogGrid({ clusters }: CatalogGridProps) {
  if (clusters.length === 0) {
    return <EmptyState />
  }

  return (
    <div
      style={{ padding: '16px 16px 40px' }}
      className="catalog-grid"
    >
      <div className="catalog-grid-inner">
        {clusters.map(cluster => (
          <EditionCard key={cluster.clusterKey} cluster={cluster} />
        ))}
      </div>
    </div>
  )
}

export default CatalogGrid
