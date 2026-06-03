import { notFound } from 'next/navigation'
import { clusterBySlug, allSlugs } from '@/lib/data'
import { ItemHero } from '@/components/item/ItemHero'
import { MetaTable } from '@/components/item/MetaTable'
import { ExtrasSection } from '@/components/item/ExtrasSection'
import { SourcesList } from '@/components/item/SourcesList'
import { BackLink } from '@/components/modules/BackLink'
import { formatDate } from '@/lib/format'

type Props = {
  params: Promise<{ slug: string }>
  searchParams: Promise<{ from?: string }>
}

export default async function ItemPage({ params, searchParams }: Props) {
  const { slug } = await params
  const { from } = await searchParams
  const cluster = clusterBySlug(slug)

  if (!cluster) notFound()

  const { canonical, items } = cluster

  // Back navigation:
  //   from=edition:<editionKey>  → back to the edition page
  //   from=/?q=...&page=N        → back to catalog preserving filters + page
  //   (absent)                   → catalog root
  let backHref = '/'
  let backLabel = 'Catálogo'
  if (from?.startsWith('edition:')) {
    backHref = `/edition/${from.slice(8)}`
    backLabel = cluster.editionDisplay || cluster.seriesDisplay || 'Edición'
  } else if (from) {
    backHref = from
  }

  const hasExtras = (canonical.extras?.length ?? 0) > 0

  // Modelo 1-fila-por-producto: las fuentes viven en canonical.sources[].
  // Fallback a derivarlas de las filas del cluster (datos legacy sin sources[]).
  const sources = (canonical.sources && canonical.sources.length)
    ? canonical.sources
    : items.map(it => ({
        name: it.source, url: it.url, price: it.price,
        release_date: it.release_date, stock_type: it.stock_type,
        country: it.country, publisher: it.publisher,
      }))
  const hasMultipleSources = sources.length > 1

  return (
    <main style={{ maxWidth: 1024, margin: '0 auto', padding: '24px 16px 64px' }}>
      <BackLink href={backHref} label={backLabel} />

      <article>
        <ItemHero cluster={cluster} />

        {/* Meta + extras grid */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: hasExtras ? 'repeat(auto-fit, minmax(260px, 1fr))' : '1fr',
          gap: 32,
          marginTop: 8,
          paddingTop: 24,
          borderTop: '1px solid var(--color-border)',
        }}>
          <MetaTable item={canonical} />
          {hasExtras && <ExtrasSection extras={canonical.extras!} />}
        </div>

        {/* Multi-source table */}
        {hasMultipleSources && (
          <div style={{
            marginTop: 32,
            paddingTop: 24,
            borderTop: '1px solid var(--color-border)',
          }}>
            <SourcesList sources={sources} />
          </div>
        )}
      </article>
    </main>
  )
}

export async function generateStaticParams() {
  return allSlugs().map(slug => ({ slug }))
}

export async function generateMetadata({ params }: Props) {
  const { slug } = await params
  const cluster = clusterBySlug(slug)
  if (!cluster) return {}

  const { canonical } = cluster
  const parts = [
    canonical.edition_display,
    canonical.publisher,
    canonical.country,
    canonical.price,
    canonical.release_date && `Lanzamiento: ${formatDate(canonical.release_date)}`,
  ].filter(Boolean)

  return {
    title: `${canonical.title} — PandaWatch`,
    description: parts.join(' · ') || undefined,
    openGraph: {
      type: 'book',
      images: canonical.image_url ? [canonical.image_url] : [],
    },
  }
}
