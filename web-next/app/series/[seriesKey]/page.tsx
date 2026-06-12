import { notFound } from 'next/navigation'
import { seriesByKey, loadSeriesEditions, allSeriesKeys } from '@/lib/data'
import { SeriesHeader } from '@/components/series/SeriesHeader'
import { CatalogGrid } from '@/components/catalog/CatalogGrid'
import { BackLink } from '@/components/modules/BackLink'
import { JsonLd } from '@/components/seo/JsonLd'
import { seriesDescription } from '@/lib/descriptions'
import { seriesJsonLd, breadcrumbJsonLd } from '@/lib/jsonld'
import { ogImage, decodeRouteParam, seriesPath } from '@/lib/seo'
import type { Metadata } from 'next'

type Props = {
  params: Promise<{ seriesKey: string }>
}

// Sólo las series de generateStaticParams existen — render 100% estático.
export const dynamicParams = false

export default async function SeriesPage({ params }: Props) {
  const seriesKey = decodeRouteParam((await params).seriesKey)
  const series = seriesByKey(seriesKey)
  if (!series) notFound()

  const editions = loadSeriesEditions(seriesKey)

  const trail = [
    { name: 'Inicio', path: '/' },
    { name: series.seriesDisplay, path: seriesPath(seriesKey) },
  ]

  return (
    <main style={{ maxWidth: 1280, margin: '0 auto', padding: '24px 16px 64px' }}>
      <JsonLd data={[seriesJsonLd(series, editions, seriesKey), breadcrumbJsonLd(trail)]} />
      <BackLink fallbackHref="/" label="Catálogo" />
      <SeriesHeader series={series} />
      <CatalogGrid clusters={editions} />
    </main>
  )
}

export async function generateStaticParams() {
  return allSeriesKeys().map(seriesKey => ({ seriesKey }))
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const seriesKey = decodeRouteParam((await params).seriesKey)
  const series = seriesByKey(seriesKey)
  if (!series) return {}

  const title = series.seriesDisplay
  const description = seriesDescription(series)
  const path = seriesPath(seriesKey)
  const images = ogImage(series.cover.imageLocal ?? series.cover.imageUrl, title)

  return {
    title,
    description,
    alternates: { canonical: path },
    openGraph: { type: 'website', url: path, title, description, images },
    twitter: { card: 'summary_large_image', title, description },
  }
}
