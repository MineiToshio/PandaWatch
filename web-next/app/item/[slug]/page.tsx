import { notFound } from 'next/navigation'
import { clusterBySlug, allSlugs, coverImage } from '@/lib/data'
import { ItemHero } from '@/components/item/ItemHero'
import { MetaTable } from '@/components/item/MetaTable'
import { ExtrasSection } from '@/components/item/ExtrasSection'
import { SourcesList } from '@/components/item/SourcesList'
import { BackLink } from '@/components/modules/BackLink'
import { JsonLd } from '@/components/seo/JsonLd'
import { itemDescription } from '@/lib/descriptions'
import { itemJsonLd, breadcrumbJsonLd } from '@/lib/jsonld'
import { ogImage } from '@/lib/seo'
import type { Metadata } from 'next'

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

  // Breadcrumb trail: Home → Series → Edition → Item (each level only if known).
  const trail = [{ name: 'Inicio', path: '/' }]
  if (canonical.series_key && canonical.series_display)
    trail.push({ name: canonical.series_display, path: `/series/${canonical.series_key}` })
  if (canonical.edition_key && (canonical.edition_display || cluster.editionDisplay))
    trail.push({
      name: canonical.edition_display || cluster.editionDisplay!,
      path: `/edition/${canonical.edition_key}`,
    })
  trail.push({ name: canonical.title ?? 'Ficha', path: `/item/${slug}` })

  return (
    <main style={{ maxWidth: 1024, margin: '0 auto', padding: '24px 16px 64px' }}>
      <JsonLd data={[itemJsonLd(cluster, slug), breadcrumbJsonLd(trail)]} />
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

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params
  const cluster = clusterBySlug(slug)
  if (!cluster) return {}

  const { canonical } = cluster
  const title = canonical.title ?? cluster.seriesDisplay ?? 'Ficha'
  const description = itemDescription(cluster)
  const path = `/item/${slug}`
  const cov = coverImage(canonical)
  const images = ogImage(cov.url ?? cov.local, title)

  return {
    title,
    description,
    alternates: { canonical: path },
    openGraph: {
      type: 'website',
      url: path,
      title,
      description,
      images,
    },
    twitter: { card: 'summary_large_image', title, description },
  }
}
