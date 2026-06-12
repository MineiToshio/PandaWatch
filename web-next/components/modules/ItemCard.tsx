import Link from 'next/link'
import type { Cluster } from '@/lib/types'
import { CoverImage } from '@/components/modules/CoverImage'
import { SignalChip } from '@/components/modules/SignalChip'
import { coverImage } from '@/lib/data'
import { formatDate } from '@/lib/format'

type ItemCardProps = {
  cluster: Cluster
  from?: string
}

export function ItemCard({ cluster, from }: ItemCardProps) {
  const { canonical, signalTypes, slug } = cluster
  const href = slug
    ? `/item/${slug}${from ? `?from=${encodeURIComponent(from)}` : ''}`
    : '#'

  const visibleSignals = signalTypes.slice(0, 2)

  return (
    <Link
      href={href}
      className="item-card"
      style={{
        display: 'block',
        borderRadius: 'var(--radius-md)',
        border: '1px solid var(--color-border)',
        background: 'var(--color-surface)',
        overflow: 'hidden',
        textDecoration: 'none',
        color: 'inherit',
        transition: 'box-shadow var(--duration-normal), transform var(--duration-normal)',
      }}
    >
      {/* Cover area */}
      <div style={{ position: 'relative', aspectRatio: '2/3', background: 'var(--ink-100)' }}>
        <CoverImage
          imageLocal={coverImage(canonical).local}
          imageUrl={coverImage(canonical).url}
          alt={canonical.title || 'Portada'}
          fill
          sizes="(max-width: 640px) 33vw, (max-width: 1024px) 20vw, 15vw"
        />

        {/* Volume badge — top left */}
        {canonical.volume && (
          <div
            style={{
              position: 'absolute',
              top: 6,
              left: 6,
              background: 'rgba(0,0,0,0.75)',
              color: '#fff',
              fontSize: 10,
              fontWeight: 700,
              padding: '2px 6px',
              borderRadius: 'var(--radius-sm)',
              lineHeight: 1.4,
            }}
          >
            Vol.&nbsp;{canonical.volume}
          </div>
        )}

      </div>

      {/* Info section */}
      <div style={{ padding: '10px 10px 12px' }}>
        <p
          style={{
            fontSize: 13,
            fontWeight: 600,
            fontFamily: 'var(--font-display)',
            color: 'var(--color-text-primary)',
            lineHeight: 1.3,
            marginBottom: 4,
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
        >
          {canonical.title || 'Sin título'}
        </p>

        {canonical.price && parseFloat(canonical.price.replace(/[^0-9.,]/g, '').replace(',', '.') || '0') > 0 && (
          <p
            style={{
              fontSize: 12,
              fontWeight: 700,
              color: 'var(--color-secondary)',
              marginBottom: 3,
            }}
          >
            {canonical.price}
          </p>
        )}

        {canonical.release_date && (
          <p
            style={{
              fontSize: 11,
              color: 'var(--color-text-tertiary)',
              marginBottom: 5,
            }}
          >
            {formatDate(canonical.release_date)}
          </p>
        )}

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

export default ItemCard
