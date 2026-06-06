import { notFound } from 'next/navigation'
import { loadEditionClusters, allEditionKeys } from '@/lib/data'
import { EditionHeader } from '@/components/edition/EditionHeader'
import { VolumeGrid } from '@/components/edition/VolumeGrid'
import { BackLink } from '@/components/modules/BackLink'
import { JsonLd } from '@/components/seo/JsonLd'
import { editionDescription } from '@/lib/descriptions'
import { editionJsonLd, breadcrumbJsonLd } from '@/lib/jsonld'
import { ogImage } from '@/lib/seo'
import type { Metadata } from 'next'

type Props = {
  params: Promise<{ editionKey: string }>
  searchParams: Promise<{ from?: string }>
}

export default async function EditionPage({ params, searchParams }: Props) {
  const { editionKey } = await params
  const { from } = await searchParams
  const clusters = loadEditionClusters(editionKey)

  if (!clusters.length) notFound()

  const firstCluster = clusters[0]
  const allSignalTypes = [...new Set(clusters.flatMap(c => c.signalTypes))]
  const c = firstCluster.canonical

  const trail = [{ name: 'Inicio', path: '/' }]
  if (c.series_key && (c.series_display || firstCluster.seriesDisplay))
    trail.push({
      name: c.series_display || firstCluster.seriesDisplay!,
      path: `/series/${c.series_key}`,
    })
  trail.push({
    name: firstCluster.editionDisplay ?? firstCluster.seriesDisplay ?? editionKey,
    path: `/edition/${editionKey}`,
  })

  return (
    <main style={{ maxWidth: 1280, margin: '0 auto', padding: '24px 16px 64px' }}>
      <JsonLd
        data={[
          editionJsonLd(firstCluster, clusters, editionKey, clusters.length, allSignalTypes),
          breadcrumbJsonLd(trail),
        ]}
      />
      <BackLink href={from || '/'} label="Catálogo" />
      <EditionHeader
        cluster={firstCluster}
        totalVolumes={clusters.length}
        signalTypes={allSignalTypes}
      />
      <VolumeGrid clusters={clusters} editionKey={editionKey} />
    </main>
  )
}

export async function generateStaticParams() {
  return allEditionKeys().map(editionKey => ({ editionKey }))
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { editionKey } = await params
  const clusters = loadEditionClusters(editionKey)
  if (!clusters.length) return {}

  const first = clusters[0]
  const { canonical } = first
  const allSignalTypes = [...new Set(clusters.flatMap(c => c.signalTypes))]
  const title = canonical.edition_display || canonical.series_display || editionKey
  const description = editionDescription(first, clusters.length, allSignalTypes)
  const path = `/edition/${editionKey}`
  const images = ogImage(canonical.image_url ?? canonical.image_local, title)

  return {
    title,
    description,
    alternates: { canonical: path },
    openGraph: { type: 'website', url: path, title, description, images },
    twitter: { card: 'summary_large_image', title, description },
  }
}
