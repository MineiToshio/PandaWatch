import { ImageCarousel } from '@/components/item/ImageCarousel'
import { SignalChip } from '@/components/modules/SignalChip'
import { CountryFlag } from '@/components/modules/CountryFlag'
import { RarityBadge } from '@/components/modules/RarityBadge'
import { formatDate } from '@/lib/format'
import { itemDescription } from '@/lib/descriptions'
import { coverImage } from '@/lib/data'
import { dedupeImages, imageKey } from '@/lib/images'
import type { Cluster, ItemImage } from '@/lib/types'

export function ItemHero({ cluster }: { cluster: Cluster }) {
  const { canonical, signalTypes } = cluster

  // El carrusel muestra la UNION de images[] de todas las fuentes del cluster,
  // con la portada de la canónica (images[0], la que se ve en la card) primera.
  // Mismo invariante que web/index.html: carrusel[0] == card, y el detalle no
  // depende de qué fila quedó como canónica. Dedup compartido (lib/images).
  const candidates: ItemImage[] = []
  // images[0] de la canónica = fuente de verdad de la portada; legacy fallback.
  const cov = coverImage(canonical)
  if (cov.url || cov.local) {
    const own = (canonical.images ?? []).find(im => imageKey(im.url) === imageKey(cov.url))
    candidates.push(own ?? { url: cov.url ?? '', local: cov.local, kind: 'gallery' })
  }
  for (const it of cluster.items) {
    candidates.push(...(it.images ?? []))
  }
  const images = dedupeImages(candidates)

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
              Título original: {canonical.title_original}
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

          {/* Signal chips */}
          {signalTypes.length > 0 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              {signalTypes.map(s => (
                <SignalChip key={s} signal={s} size="md" />
              ))}
            </div>
          )}

          {/* Rarity badge — misma fuente única que EditionCard/SidebarFilters */}
          {canonical.rarity && (
            <RarityBadge rarity={canonical.rarity} style={{ alignSelf: 'flex-start' }} />
          )}

          {/* Key info */}
          <div style={{ paddingTop: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
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

          {/* Description — stored description_es/description, o template determinístico
              (FRD-008 FR-6). Siempre presente: contenido indexable. */}
          <p style={{
            fontSize: 14, lineHeight: 1.6,
            color: 'var(--color-text-secondary)', margin: 0,
          }}>
            {itemDescription(cluster)}
          </p>
        </div>
      </div>
    </>
  )
}

export default ItemHero
