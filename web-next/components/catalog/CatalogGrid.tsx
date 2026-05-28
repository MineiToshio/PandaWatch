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
      style={{ padding: '16px 16px 32px' }}
      className="catalog-grid"
    >
      <style>{`
        .catalog-grid-inner {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 16px;
        }
        @media (min-width: 480px) {
          .catalog-grid-inner { grid-template-columns: repeat(3, 1fr); }
        }
        @media (min-width: 768px) {
          .catalog-grid-inner { grid-template-columns: repeat(3, 1fr); }
        }
        @media (min-width: 1024px) {
          .catalog-grid-inner { grid-template-columns: repeat(4, 1fr); }
        }
        @media (min-width: 1280px) {
          .catalog-grid-inner { grid-template-columns: repeat(5, 1fr); }
        }
        .edition-card:hover {
          box-shadow: var(--shadow-md);
          transform: translateY(-2px);
        }
      `}</style>
      <div className="catalog-grid-inner">
        {clusters.map(cluster => (
          <EditionCard key={cluster.clusterKey} cluster={cluster} />
        ))}
      </div>
    </div>
  )
}

export default CatalogGrid
