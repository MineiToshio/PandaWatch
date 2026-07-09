import Link from 'next/link'
import type { Cluster } from '@/lib/types'
import { coverImage } from '@/lib/data'
import { editionPath, itemPath } from '@/lib/seo'
import { CoverImage } from '@/components/modules/CoverImage'
import { SignalChip } from '@/components/modules/SignalChip'
import { EditionTypeChip } from '@/components/modules/EditionTypeChip'
import { editionTypeLabel, editionSlugFromKey } from '@/lib/format'
import { equivSignalsForSlug } from '@/lib/vocab'
import { CountryFlag } from '@/components/modules/CountryFlag'
import { RarityBadge } from '@/components/modules/RarityBadge'

type EditionCardProps = {
  cluster: Cluster
  /** Portada above-the-fold → carga eager (LCP). */
  priority?: boolean
}

export function EditionCard({ cluster, priority = false }: EditionCardProps) {
  const { canonical, signalTypes, volumeCount, countries, slug } = cluster
  const leaves = Math.min(volumeCount, 3) as 1 | 2 | 3

  // Multi-volume editions → /edition/[editionKey]
  // Single-volume editions + standalone items → /item/[slug]  (FRD-003)
  // Hrefs limpios (sin ?from=): el back-state vive en BackLink/sessionStorage,
  // y robots.txt bloquea /*? — un querystring acá esconde el link a crawlers.
  const href = (cluster.editionKey && volumeCount > 1)
    ? editionPath(cluster.editionKey)
    : (slug ? itemPath(slug) : '#')

  // Chip del TIPO de edición (desde edition_key — el title oficial ya no lo
  // lleva inyectado) + signal chips. Máximo 2 chips para mantener la tarjeta
  // compacta: con chip de edición entra 1 signal, sin él entran 2.
  const editionType = editionTypeLabel(cluster.canonical.edition_key)
  const equivSignals = equivSignalsForSlug(editionSlugFromKey(cluster.canonical.edition_key))
  const candidateSignals = editionType
    ? signalTypes.filter(s => !equivSignals.includes(s))
    : signalTypes
  const visibleSignals = candidateSignals.slice(0, editionType ? 1 : 2)

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
            priority={priority}
            sizes="(max-width: 640px) 50vw, (max-width: 1024px) 33vw, 20vw"
          />

          {/* Rarity badge — top left, glassy dark pill */}
          {canonical.rarity && (
            <RarityBadge
              rarity={canonical.rarity}
              style={{ position: 'absolute', top: 8, left: 8, zIndex: 2 }}
            />
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
            {editionType && (
              <EditionTypeChip editionKey={cluster.canonical.edition_key} size="sm" />
            )}
            {visibleSignals.map(s => (
              <SignalChip key={s} signal={s} size="sm" />
            ))}
            {candidateSignals.length > visibleSignals.length && (
              <span
                style={{
                  fontSize: 10,
                  color: 'var(--color-text-tertiary)',
                  alignSelf: 'center',
                }}
              >
                +{candidateSignals.length - visibleSignals.length}
              </span>
            )}
          </div>
        </div>

      </div>{/* /.edition-card-inner */}
    </Link>
  )
}

export default EditionCard
