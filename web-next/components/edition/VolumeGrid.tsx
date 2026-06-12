import { ItemCard } from '@/components/modules/ItemCard'
import type { Cluster } from '@/lib/types'

type VolumeGridProps = {
  clusters: Cluster[]
}

export function VolumeGrid({ clusters }: VolumeGridProps) {
  return (
    <div>
      <style>{`
        .volume-grid {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 16px;
          list-style: none;
          padding: 0;
          margin: 0;
        }
        @media (min-width: 480px) {
          .volume-grid { grid-template-columns: repeat(3, 1fr); }
        }
        @media (min-width: 1024px) {
          .volume-grid { grid-template-columns: repeat(4, 1fr); }
        }
        @media (min-width: 1280px) {
          .volume-grid { grid-template-columns: repeat(5, 1fr); }
        }
      `}</style>
      <ul role="list" className="volume-grid">
        {clusters.map(cluster => (
          <li key={cluster.clusterKey}>
            <ItemCard cluster={cluster} />
          </li>
        ))}
      </ul>
    </div>
  )
}

export default VolumeGrid
