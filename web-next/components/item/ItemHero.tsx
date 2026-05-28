import { ImageCarousel } from '@/components/item/ImageCarousel'
import { SignalChip } from '@/components/modules/SignalChip'
import { ScoreBadge } from '@/components/modules/ScoreBadge'
import { CountryFlag } from '@/components/modules/CountryFlag'
import { formatDate } from '@/lib/format'
import type { Cluster } from '@/lib/types'

export function ItemHero({ cluster }: { cluster: Cluster }) {
  const { canonical, signalTypes } = cluster

  const images = canonical.images?.length
    ? canonical.images
    : (canonical.image_url || canonical.image_local)
      ? [{ url: canonical.image_url ?? '', local: canonical.image_local, kind: 'cover' as const }]
      : []

  return (
    <>
      <style>{`
        .item-hero {
          display: grid;
          grid-template-columns: 1fr;
          gap: 24px;
          margin-bottom: 32px;
        }
        @media (min-width: 640px) {
          .item-hero {
            grid-template-columns: 280px 1fr;
            gap: 32px;
            align-items: start;
          }
        }
      `}</style>

      <div className="item-hero">
        {/* Left column — image carousel */}
        <div>
          <ImageCarousel images={images} alt={canonical.title ?? 'Portada'} />
        </div>

        {/* Right column — metadata */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>

          {/* Eyebrow: series name */}
          {canonical.series_display && (
            <p style={{
              fontSize: 11, fontWeight: 600,
              textTransform: 'uppercase', letterSpacing: '0.08em',
              color: 'var(--color-text-tertiary)', margin: 0,
            }}>
              {canonical.series_display}
            </p>
          )}

          {/* Title */}
          <h1 style={{
            fontSize: 28, fontWeight: 700,
            fontFamily: 'var(--font-display)',
            color: 'var(--color-text-primary)',
            lineHeight: 1.2, margin: 0,
          }}>
            {canonical.title}
          </h1>

          {/* Original title (if different) */}
          {canonical.title_original && canonical.title_original !== canonical.title && (
            <p style={{
              fontSize: 13, fontStyle: 'italic',
              color: 'var(--color-text-tertiary)', margin: 0,
            }}>
              原題: {canonical.title_original}
            </p>
          )}

          {/* Publisher + country + language */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            {canonical.country && (
              <CountryFlag country={canonical.country} showLabel />
            )}
            {canonical.publisher && (
              <span style={{ fontSize: 13, color: 'var(--color-text-secondary)' }}>
                · {canonical.publisher}
              </span>
            )}
            {canonical.language && (
              <span style={{ fontSize: 13, color: 'var(--color-text-secondary)' }}>
                · {canonical.language}
              </span>
            )}
          </div>

          {/* Score + signal chips */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            {canonical.score !== undefined && (
              <ScoreBadge score={canonical.score} showLabel />
            )}
            {signalTypes.map(s => (
              <SignalChip key={s} signal={s} size="md" />
            ))}
          </div>

          {/* Key purchase info */}
          <div style={{ paddingTop: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
            {canonical.price && (
              <p style={{ fontSize: 24, fontWeight: 700, color: 'var(--vermillion-500)', margin: 0 }}>
                {canonical.price}
              </p>
            )}
            {canonical.release_date && (
              <p style={{ fontSize: 13, color: 'var(--color-text-secondary)', margin: 0 }}>
                Lanzamiento: {formatDate(canonical.release_date)}
              </p>
            )}
            {canonical.isbn && (
              <p style={{ fontSize: 12, color: 'var(--color-text-tertiary)', margin: 0 }}>
                ISBN: {canonical.isbn}
              </p>
            )}
          </div>

          {/* Description — description_es con fallback a description */}
          {(canonical.description_es || canonical.description) && (
            <p style={{
              fontSize: 14, lineHeight: 1.6,
              color: 'var(--color-text-secondary)', margin: 0,
            }}>
              {canonical.description_es || canonical.description}
            </p>
          )}
        </div>
      </div>
    </>
  )
}

export default ItemHero
