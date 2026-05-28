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

  // Editions → /edition/[editionKey]; standalone items → /item/[slug]  (FRD-003)
  const href = cluster.editionKey ? `/edition/${cluster.editionKey}` : (slug ? `/item/${slug}` : '#')

  // Show at most 2 signal chips to keep card compact
  const visibleSignals = signalTypes.slice(0, 2)

  return (
    // Outer wrapper: owns the stack pseudo-elements and hover lift.
    // NO overflow:hidden here — the brownish layers need to peek outside the card boundary.
    // All visual card styles (bg, border, overflow) live on .edition-card-inner below.
    <Link
      href={href}
      className="edition-card"
      data-leaves={leaves}
    >
      {/* Inner surface — clips content and provides solid white background that
          covers the pseudo-elements within the card area, preventing bleed-through. */}
      <div className="edition-card-inner">

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

        {/* Info — fixed height so every card (single or stacked) is identical.
            Three slots with reserved space; shorter content leaves empty space
            at the bottom instead of shrinking the card. */}
        <div
          style={{
            padding: '10px 10px 12px',
            height: 96,
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
          }}
        >
          {/* Series name — slot always reserved (fixed height) for uniform layout */}
          <p
            style={{
              fontSize: 10,
              fontWeight: 500,
              color: 'var(--color-text-secondary)',
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              height: 14,
              lineHeight: '12px',
              marginBottom: 2,
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}
          >
            {canonical.series_display || ' '}
          </p>

          {/* Title — reserved height for up to 2 lines */}
          <p
            style={{
              fontSize: 13,
              fontWeight: 600,
              fontFamily: 'var(--font-display)',
              color: 'var(--color-text-primary)',
              lineHeight: 1.3,
              height: 34,
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden',
              marginBottom: 6,
            }}
          >
            {canonical.title || 'Sin título'}
          </p>

          {/* Signal chips — anchored to the bottom of the fixed-height info block */}
          <div style={{ display: 'flex', flexWrap: 'nowrap', gap: 4, marginTop: 'auto', minHeight: 18, overflow: 'hidden' }}>
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
        </div>

      </div>{/* /.edition-card-inner */}
    </Link>
  )
}

export default EditionCard
