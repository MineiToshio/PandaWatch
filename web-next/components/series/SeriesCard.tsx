import Link from 'next/link'
import type { Series } from '@/lib/types'
import { seriesPath } from '@/lib/seo'
import { CoverImage } from '@/components/modules/CoverImage'
import { CountryFlag } from '@/components/modules/CountryFlag'

type SeriesCardProps = {
  series: Series
}

export function SeriesCard({ series }: SeriesCardProps) {
  const { seriesKey, seriesDisplay, cover, editionCount, itemCount, countries } = series

  const edLabel = editionCount === 1 ? 'edición' : 'ediciones'
  const tomoLabel = itemCount === 1 ? 'tomo' : 'tomos'

  return (
    <Link
      href={seriesPath(seriesKey)}
      style={{
        display: 'block',
        textDecoration: 'none',
        borderRadius: 'var(--radius-sm)',
        overflow: 'hidden',
        background: 'var(--color-surface)',
        border: '1px solid var(--color-border)',
        transition: 'transform 0.15s ease, box-shadow 0.15s ease',
      }}
      className="series-card"
    >
      {/* Cover — use paddingBottom trick instead of aspect-ratio so next/image
          fill gets a real computed height at mount time */}
      <div
        style={{
          position: 'relative',
          paddingBottom: '150%',
          background: 'var(--ink-100)',
          overflow: 'hidden',
        }}
      >
        <CoverImage
          imageLocal={cover.imageLocal}
          imageUrl={cover.imageUrl}
          alt={seriesDisplay}
          fill
          sizes="160px"
        />

        {/* Country flags — bottom left over cover */}
        {countries.length > 0 && (
          <div
            style={{
              position: 'absolute',
              bottom: 6,
              left: 6,
              display: 'flex',
              gap: 3,
              flexWrap: 'wrap',
            }}
          >
            {countries.slice(0, 3).map(c => (
              <CountryFlag key={c} country={c} />
            ))}
          </div>
        )}
      </div>

      {/* Info block — fixed height for uniform alignment */}
      <div
        style={{
          padding: '8px 10px 10px',
          height: 64,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {/* Series name */}
        <p
          style={{
            fontSize: 13,
            fontWeight: 600,
            fontFamily: 'var(--font-display)',
            color: 'var(--color-text-primary)',
            lineHeight: 1.3,
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
            margin: 0,
          }}
        >
          {seriesDisplay}
        </p>

        {/* Stats line */}
        <p
          style={{
            fontSize: 11,
            color: 'var(--color-text-tertiary)',
            margin: '4px 0 0',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}
        >
          {editionCount} {edLabel} · {itemCount} {tomoLabel}
        </p>
      </div>
    </Link>
  )
}

export default SeriesCard
