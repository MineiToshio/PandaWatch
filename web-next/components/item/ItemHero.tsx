import { ImageCarousel } from '@/components/item/ImageCarousel'
import { SignalChip } from '@/components/modules/SignalChip'
import { CountryFlag } from '@/components/modules/CountryFlag'
import { formatDate } from '@/lib/format'
import { itemDescription } from '@/lib/descriptions'
import type { Cluster, ItemImage } from '@/lib/types'

const RARITY_META: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
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

export function ItemHero({ cluster }: { cluster: Cluster }) {
  const { canonical, signalTypes } = cluster

  // El carrusel muestra la UNION de images[] de todas las fuentes del cluster,
  // con la portada de la canónica (image_url, la que se ve en la card) primera.
  // Mismo invariante que web/index.html: carrusel[0] == card, y el detalle no
  // depende de qué fila quedó como canónica. Dedup por URL (sin esquema/query).
  const imgKey = (u?: string) =>
    (u ?? '').split('?')[0].replace(/^https?:\/\//, '').toLowerCase()
  const seen = new Set<string>()
  const images: ItemImage[] = []
  const pushImg = (im?: ItemImage) => {
    if (!im?.url) return
    const k = imgKey(im.url)
    if (seen.has(k)) return
    seen.add(k)
    images.push(im)
  }
  if (canonical.image_url || canonical.image_local) {
    const own = (canonical.images ?? []).find(im => imgKey(im.url) === imgKey(canonical.image_url))
    pushImg(own ?? { url: canonical.image_url ?? '', local: canonical.image_local, kind: 'gallery' })
  }
  for (const it of cluster.items) {
    for (const im of it.images ?? []) pushImg(im)
  }

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

          {/* Rarity badge — same visual as EditionCard's RarityBadge */}
          {canonical.rarity && RARITY_META[canonical.rarity] && (() => {
            const rm = RARITY_META[canonical.rarity!]
            return (
              <div
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 4,
                  padding: '4px 8px',
                  borderRadius: 5,
                  fontSize: 10,
                  fontWeight: 600,
                  fontFamily: 'var(--font-display)',
                  color: rm.color,
                  background: 'rgba(20,17,14,0.82)',
                  backdropFilter: 'blur(6px)',
                  border: '1px solid rgba(255,255,255,0.12)',
                  alignSelf: 'flex-start',
                }}
              >
                {rm.icon}
                {rm.label}
              </div>
            )
          })()}

          {/* Key purchase info */}
          <div style={{ paddingTop: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
            {canonical.price && parseFloat(canonical.price.replace(/[^0-9.,]/g, '').replace(',', '.') || '0') > 0 && (
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
