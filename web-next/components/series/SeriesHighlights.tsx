import type { Series } from '@/lib/types'
import { SeriesCard } from './SeriesCard'

type SeriesHighlightsProps = {
  series: Series[]
}

export function SeriesHighlights({ series }: SeriesHighlightsProps) {
  if (!series?.length) return null

  return (
    <section style={{ padding: '16px 16px 8px' }}>
      <h2
        style={{
          fontFamily: 'var(--font-display)',
          fontSize: 15,
          fontWeight: 700,
          color: 'var(--color-text-primary)',
          margin: '0 0 2px',
        }}
      >
        Obras destacadas
      </h2>
      <p
        style={{
          fontSize: 12,
          color: 'var(--color-text-tertiary)',
          margin: '0 0 10px',
        }}
      >
        Las series con más ediciones especiales en el catálogo.
      </p>
      <div
        className="series-strip"
        style={{
          display: 'flex',
          gap: 10,
          overflowX: 'auto',
          paddingBottom: 4,
          scrollSnapType: 'x proximity',
        }}
      >
        {series.map(s => (
          <div
            key={s.seriesKey}
            style={{ flex: '0 0 auto', width: 192, scrollSnapAlign: 'start' }}
          >
            <SeriesCard series={s} />
          </div>
        ))}
      </div>
    </section>
  )
}

export default SeriesHighlights
