import { CoverImage } from '@/components/modules/CoverImage'
import { SignalChip } from '@/components/modules/SignalChip'
import { CountryFlag } from '@/components/modules/CountryFlag'
import type { Series } from '@/lib/types'

type SeriesHeaderProps = {
  series: Series
}

export function SeriesHeader({ series }: SeriesHeaderProps) {
  const { seriesDisplay, cover, editionCount, itemCount, countries, signalTypes } = series

  const edLabel = editionCount === 1 ? 'edición' : 'ediciones'
  const tomoLabel = itemCount === 1 ? 'tomo' : 'tomos'

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
            imageLocal={cover.imageLocal}
            imageUrl={cover.imageUrl}
            alt={seriesDisplay}
            fill
            sizes="64px"
            priority
          />
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          {/* Country flags row */}
          {countries.length > 0 && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                marginBottom: 6,
                flexWrap: 'wrap',
              }}
            >
              {countries.slice(0, 5).map(c => (
                <CountryFlag key={c} country={c} showLabel={false} />
              ))}
            </div>
          )}

          {/* Series name */}
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
            {seriesDisplay}
          </h1>

          {/* Stats */}
          <div style={{ marginTop: 8 }}>
            <span style={{ fontSize: 13, color: 'var(--color-text-tertiary)' }}>
              {editionCount} {edLabel} · {itemCount} {tomoLabel}
            </span>
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

export default SeriesHeader
