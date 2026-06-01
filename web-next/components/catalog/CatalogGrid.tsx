import type { Cluster } from '@/lib/types'
import { EditionCard } from './EditionCard'
import { EmptyState } from './EmptyState'

type CatalogGridProps = {
  clusters: Cluster[]
  from?: string
}

export function CatalogGrid({ clusters, from }: CatalogGridProps) {
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
          <EditionCard key={cluster.clusterKey} cluster={cluster} from={from} />
        ))}
      </div>
    </div>
  )
}

export default CatalogGrid
