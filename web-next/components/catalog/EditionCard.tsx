import Link from 'next/link'
import type { Cluster } from '@/lib/types'
import { coverImage } from '@/lib/data'
import { CoverImage } from '@/components/modules/CoverImage'
import { SignalChip } from '@/components/modules/SignalChip'
import { CountryFlag } from '@/components/modules/CountryFlag'

type EditionCardProps = {
  cluster: Cluster
  from?: string
}

export function EditionCard({ cluster, from }: EditionCardProps) {
  const { canonical, signalTypes, volumeCount, countries, slug } = cluster
  const leaves = Math.min(volumeCount, 3) as 1 | 2 | 3

  // Multi-volume editions → /edition/[editionKey]
  // Single-volume editions + standalone items → /item/[slug]  (FRD-003)
  const baseHref = (cluster.editionKey && volumeCount > 1)
    ? `/edition/${cluster.editionKey}`
    : (slug ? `/item/${slug}` : '#')
  const href = (from && baseHref !== '#')
    ? `${baseHref}?from=${encodeURIComponent(from)}`
    : baseHref

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
            imageLocal={coverImage(canonical).local}
            imageUrl={coverImage(canonical).url}
            alt={canonical.title || 'Portada'}
            fill
            sizes="(max-width: 640px) 50vw, (max-width: 1024px) 33vw, 20vw"
          />

          {/* Rarity badge — top left, glassy dark pill */}
          {canonical.rarity && <RarityBadge rarity={canonical.rarity} />}

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

// ─── Rarity badge ────────────────────────────────────────────────────────────

const RARITY_META: Record<
  'common' | 'rare' | 'super_rare' | 'ultra_rare',
  { label: string; color: string; icon: React.ReactNode }
> = {
  common: {
    label: 'Accessible',
    color: '#9CA3AF',
    icon: (
      <svg width={9} height={9} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
        <circle cx={12} cy={12} r={10} />
      </svg>
    ),
  },
  rare: {
    label: 'Rare',
    color: '#8BA8F8',
    icon: (
      <svg width={9} height={9} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
      </svg>
    ),
  },
  super_rare: {
    label: 'Super Rare',
    color: '#C4A8FF',
    icon: (
      <svg width={9} height={9} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <path d="M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5z" />
      </svg>
    ),
  },
  ultra_rare: {
    label: 'Ultra Rare',
    color: '#FDE68A',
    icon: (
      <svg width={9} height={9} viewBox="0 0 24 24" fill="currentColor">
        <path d="M6 3h12l4 6-10 13L2 9z" />
      </svg>
    ),
  },
}

function RarityBadge({ rarity }: { rarity: 'common' | 'rare' | 'super_rare' | 'ultra_rare' }) {
  const meta = RARITY_META[rarity]
  return (
    <div
      style={{
        position: 'absolute',
        top: 8,
        left: 8,
        zIndex: 2,
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        padding: '4px 8px',
        borderRadius: 5,
        fontSize: 10,
        fontWeight: 600,
        fontFamily: 'var(--font-display)',
        color: meta.color,
        background: 'rgba(20,17,14,0.82)',
        backdropFilter: 'blur(6px)',
        border: '1px solid rgba(255,255,255,0.12)',
      }}
    >
      {meta.icon}
      {meta.label}
    </div>
  )
}

export default EditionCard
