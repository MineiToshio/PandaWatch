import Link from 'next/link'
import type { Cluster } from '@/lib/types'
import { CoverImage } from '@/components/modules/CoverImage'
import { SignalChip } from '@/components/modules/SignalChip'
import { ScoreBadge } from '@/components/modules/ScoreBadge'
import { CountryFlag } from '@/components/modules/CountryFlag'

type EditionCardProps = {
  cluster: Cluster
}

export function EditionCard({ cluster }: EditionCardProps) {
  const { canonical, signalTypes, volumeCount, countries, slug } = cluster
  const leaves = Math.min(volumeCount, 3) as 1 | 2 | 3

  const href = slug ? `/item/${slug}` : (cluster.editionKey ? `/edition/${cluster.editionKey}` : '#')

  // Show at most 2 signal chips to keep card compact
  const visibleSignals = signalTypes.slice(0, 2)

  return (
    <Link
      href={href}
      className="edition-card"
      data-leaves={leaves}
      style={{
        display: 'block',
        borderRadius: 'var(--radius-md)',
        background: 'var(--color-surface)',
        border: '1px solid var(--color-border)',
        overflow: 'hidden',
        textDecoration: 'none',
        transition: 'box-shadow 0.15s, transform 0.15s',
        color: 'inherit',
      }}
      // hover handled via CSS below — inline styles can't do :hover
    >
      {/* Cover */}
      <div style={{ position: 'relative', aspectRatio: '2/3', background: 'var(--ink-100)' }}>
        <CoverImage
          imageLocal={canonical.image_local}
          imageUrl={canonical.image_url}
          alt={canonical.title || 'Portada'}
          fill
          sizes="(max-width: 640px) 50vw, (max-width: 1024px) 33vw, 20vw"
        />

        {/* Score badge — top right overlay */}
        {canonical.score !== undefined && (
          <div style={{ position: 'absolute', top: 8, right: 8 }}>
            <ScoreBadge score={canonical.score} />
          </div>
        )}

        {/* Country flags — bottom left */}
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

      {/* Info */}
      <div style={{ padding: '10px 10px 12px' }}>
        {/* Series name */}
        {canonical.series_display && (
          <p
            style={{
              fontSize: 10,
              fontWeight: 500,
              color: 'var(--color-text-secondary)',
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              marginBottom: 2,
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}
          >
            {canonical.series_display}
          </p>
        )}

        {/* Title */}
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
            marginBottom: 6,
          }}
        >
          {canonical.title || 'Sin título'}
        </p>

        {/* Signal chips */}
        {visibleSignals.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {visibleSignals.map(s => (
              <SignalChip key={s} signal={s} size="sm" />
            ))}
            {signalTypes.length > 2 && (
              <span
                style={{
                  fontSize: 10,
                  color: 'var(--color-text-tertiary)',
                  alignSelf: 'center',
                }}
              >
                +{signalTypes.length - 2}
              </span>
            )}
          </div>
        )}
      </div>
    </Link>
  )
}

export default EditionCard
