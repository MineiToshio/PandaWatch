import { CoverImage } from '@/components/modules/CoverImage'
import { SignalChip } from '@/components/modules/SignalChip'
import { ScoreBadge } from '@/components/modules/ScoreBadge'
import { CountryFlag } from '@/components/modules/CountryFlag'
import type { Cluster } from '@/lib/types'

type EditionHeaderProps = {
  cluster: Cluster
  totalVolumes: number
  signalTypes: string[]
}

export function EditionHeader({ cluster, totalVolumes, signalTypes }: EditionHeaderProps) {
  const { canonical } = cluster

  return (
    <header
      style={{
        marginBottom: 32,
        paddingBottom: 24,
        borderBottom: '1px solid var(--color-border)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 20 }}>
        {/* Thumbnail cover */}
        <div
          style={{
            position: 'relative',
            width: 64,
            height: 96,
            borderRadius: 'var(--radius-sm)',
            overflow: 'hidden',
            flexShrink: 0,
            background: 'var(--ink-100)',
          }}
        >
          <CoverImage
            imageLocal={canonical.image_local}
            imageUrl={canonical.image_url}
            alt={canonical.title || 'Portada'}
            fill
            sizes="64px"
            priority
          />
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          {/* Eyebrow: country flag + publisher */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              marginBottom: 6,
            }}
          >
            {canonical.country && (
              <CountryFlag country={canonical.country} showLabel={false} />
            )}
            {canonical.publisher && (
              <span
                style={{
                  fontSize: 11,
                  fontWeight: 500,
                  textTransform: 'uppercase',
                  letterSpacing: '0.08em',
                  color: 'var(--color-text-secondary)',
                }}
              >
                {canonical.publisher}
              </span>
            )}
            {canonical.country && (
              <span
                style={{
                  fontSize: 11,
                  color: 'var(--color-text-tertiary)',
                }}
              >
                {canonical.country}
              </span>
            )}
          </div>

          {/* Series name */}
          {cluster.seriesDisplay && (
            <h1
              style={{
                fontSize: 28,
                fontWeight: 700,
                fontFamily: 'var(--font-display)',
                color: 'var(--color-text-primary)',
                lineHeight: 1.2,
                margin: 0,
              }}
            >
              {cluster.seriesDisplay}
            </h1>
          )}

          {/* Edition name */}
          {cluster.editionDisplay && (
            <h2
              style={{
                fontSize: 18,
                fontWeight: 600,
                fontFamily: 'var(--font-display)',
                color: 'var(--color-text-secondary)',
                lineHeight: 1.3,
                margin: '4px 0 0',
              }}
            >
              {cluster.editionDisplay}
            </h2>
          )}

          {/* Volume count + score */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              marginTop: 10,
            }}
          >
            <span
              style={{
                fontSize: 13,
                color: 'var(--color-text-tertiary)',
              }}
            >
              {totalVolumes} {totalVolumes === 1 ? 'tomo' : 'tomos'}
            </span>
            {canonical.score !== undefined && (
              <ScoreBadge score={canonical.score} />
            )}
          </div>

          {/* Signal chips */}
          {signalTypes.length > 0 && (
            <div
              style={{
                display: 'flex',
                flexWrap: 'wrap',
                gap: 6,
                marginTop: 10,
              }}
            >
              {signalTypes.map(s => (
                <SignalChip key={s} signal={s} size="md" />
              ))}
            </div>
          )}
        </div>
      </div>
    </header>
  )
}

export default EditionHeader
