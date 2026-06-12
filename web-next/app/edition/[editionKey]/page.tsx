import { notFound } from 'next/navigation'
import { loadEditionClusters, allEditionKeys, coverImage } from '@/lib/data'
import { EditionHeader } from '@/components/edition/EditionHeader'
import { VolumeGrid } from '@/components/edition/VolumeGrid'
import { BackLink } from '@/components/modules/BackLink'
import { JsonLd } from '@/components/seo/JsonLd'
import { editionDescription } from '@/lib/descriptions'
import { editionJsonLd, breadcrumbJsonLd } from '@/lib/jsonld'
import { ogImage, decodeRouteParam, seriesPath, editionPath } from '@/lib/seo'
import type { Metadata } from 'next'

type Props = {
  params: Promise<{ editionKey: string }>
}

// Sólo las ediciones de generateStaticParams existen — render 100% estático.
export const dynamicParams = false

export default async function EditionPage({ params }: Props) {
  const editionKey = decodeRouteParam((await params).editionKey)
  const clusters = loadEditionClusters(editionKey)

  if (!clusters.length) notFound()

  const firstCluster = clusters[0]
  const allSignalTypes = [...new Set(clusters.flatMap(c => c.signalTypes))]
  const c = firstCluster.canonical

  const trail = [{ name: 'Inicio', path: '/' }]
  if (c.series_key && (c.series_display || firstCluster.seriesDisplay))
    trail.push({
      name: c.series_display || firstCluster.seriesDisplay!,
      path: seriesPath(c.series_key),
    })
  trail.push({
    name: firstCluster.editionDisplay ?? firstCluster.seriesDisplay ?? editionKey,
    path: editionPath(editionKey),
  })

  return (
    <main style={{ maxWidth: 1280, margin: '0 auto', padding: '24px 16px 64px' }}>
      <JsonLd
        data={[
          editionJsonLd(firstCluster, clusters, editionKey, clusters.length, allSignalTypes),
          breadcrumbJsonLd(trail),
        ]}
      />
      <BackLink fallbackHref="/" label="Catálogo" />
      <EditionHeader
        cluster={firstCluster}
        totalVolumes={clusters.length}
        signalTypes={allSignalTypes}
      />
      <VolumeGrid clusters={clusters} />
    </main>
  )
}

export async function generateStaticParams() {
  return allEditionKeys().map(editionKey => ({ editionKey }))
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const editionKey = decodeRouteParam((await params).editionKey)
  const clusters = loadEditionClusters(editionKey)
  if (!clusters.length) return {}

  const first = clusters[0]
  const { canonical } = first
  const allSignalTypes = [...new Set(clusters.flatMap(c => c.signalTypes))]
  const title = canonical.edition_display || canonical.series_display || editionKey
  const description = editionDescription(first, clusters.length, allSignalTypes)
  const path = editionPath(editionKey)
  const cov = coverImage(canonical)
  const images = ogImage(cov.local ?? cov.url, title)

  return {
    title,
    description,
    alternates: { canonical: path },
    openGraph: { type: 'website', url: path, title, description, images },
    twitter: { card: 'summary_large_image', title, description },
  }
}
