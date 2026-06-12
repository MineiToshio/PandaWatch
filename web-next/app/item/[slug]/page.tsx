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
import { ogImage, decodeRouteParam, seriesPath, editionPath, itemPath } from '@/lib/seo'
import type { Metadata } from 'next'

type Props = {
  params: Promise<{ slug: string }>
}

// Sólo los slugs de generateStaticParams existen — todo se resuelve en build,
// sin lecturas del JSONL en runtime. (Leer searchParams acá convertía las
// ~10k fichas en render dinámico; el back-state vive ahora en BackLink.)
export const dynamicParams = false

export default async function ItemPage({ params }: Props) {
  const slug = decodeRouteParam((await params).slug)
  const cluster = clusterBySlug(slug)

  if (!cluster) notFound()

  const { canonical, items } = cluster

  // Volver: a la edición si el item pertenece a una, si no al catálogo.
  // BackLink usa history.back() cuando hay navegación interna previa.
  const backHref = canonical.edition_key ? editionPath(canonical.edition_key) : '/'
  const backLabel = canonical.edition_key
    ? cluster.editionDisplay || cluster.seriesDisplay || 'Edición'
    : 'Catálogo'

  const hasExtras = (canonical.extras?.length ?? 0) > 0

  // Modelo 1-fila-por-producto: las fuentes viven en canonical.sources[].
  // Fallback a derivarlas de las filas del cluster (datos legacy sin sources[]).
  const sources = (canonical.sources && canonical.sources.length)
    ? canonical.sources
    : items.map(it => ({
        name: it.source, url: it.url,
        release_date: it.release_date, stock_type: it.stock_type,
        country: it.country, publisher: it.publisher,
      }))
  const hasMultipleSources = sources.length > 1

  // Breadcrumb trail: Home → Series → Edition → Item (each level only if known).
  const trail = [{ name: 'Inicio', path: '/' }]
  if (canonical.series_key && canonical.series_display)
    trail.push({ name: canonical.series_display, path: seriesPath(canonical.series_key) })
  if (canonical.edition_key && (canonical.edition_display || cluster.editionDisplay))
    trail.push({
      name: canonical.edition_display || cluster.editionDisplay!,
      path: editionPath(canonical.edition_key),
    })
  trail.push({ name: canonical.title ?? 'Ficha', path: itemPath(slug) })

  return (
    <main style={{ maxWidth: 1024, margin: '0 auto', padding: '24px 16px 64px' }}>
      <JsonLd data={[itemJsonLd(cluster, slug), breadcrumbJsonLd(trail)]} />
      <BackLink fallbackHref={backHref} label={backLabel} />

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
  const slug = decodeRouteParam((await params).slug)
  const cluster = clusterBySlug(slug)
  if (!cluster) return {}

  const { canonical } = cluster
  const title = canonical.title ?? cluster.seriesDisplay ?? 'Ficha'
  const description = itemDescription(cluster)
  const path = itemPath(slug)
  const cov = coverImage(canonical)
  // Espejo local primero: los hotlinks a tiendas son frágiles (hotlink
  // protection / links muertos) justo en el preview social.
  const images = ogImage(cov.local ?? cov.url, title)

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
