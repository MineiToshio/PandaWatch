import { notFound } from 'next/navigation'
import { loadEditionClusters, allEditionKeys } from '@/lib/data'
import { EditionHeader } from '@/components/edition/EditionHeader'
import { VolumeGrid } from '@/components/edition/VolumeGrid'
import { BackLink } from '@/components/modules/BackLink'

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

  return (
    <main style={{ maxWidth: 1280, margin: '0 auto', padding: '24px 16px 64px' }}>
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

export async function generateMetadata({ params }: Props) {
  const { editionKey } = await params
  const clusters = loadEditionClusters(editionKey)
  if (!clusters.length) return {}

  const { canonical } = clusters[0]
  return {
    title: `${canonical.edition_display || canonical.series_display || editionKey} — PandaWatch`,
    description: `${clusters.length} tomos · ${canonical.publisher ?? ''} · ${canonical.country ?? ''}`,
    openGraph: {
      images: canonical.image_url ? [canonical.image_url] : [],
    },
  }
}
