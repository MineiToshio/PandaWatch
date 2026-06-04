import { notFound } from 'next/navigation'
import { seriesByKey, loadSeriesEditions, allSeriesKeys } from '@/lib/data'
import { SeriesHeader } from '@/components/series/SeriesHeader'
import { CatalogGrid } from '@/components/catalog/CatalogGrid'
import { BackLink } from '@/components/modules/BackLink'

type Props = {
  params: Promise<{ seriesKey: string }>
  searchParams: Promise<{ from?: string }>
}

export default async function SeriesPage({ params, searchParams }: Props) {
  const { seriesKey } = await params
  const { from } = await searchParams
  const series = seriesByKey(seriesKey)
  if (!series) notFound()

  const editions = loadSeriesEditions(seriesKey)

  return (
    <main style={{ maxWidth: 1280, margin: '0 auto', padding: '24px 16px 64px' }}>
      <BackLink href={from || '/'} label="Catálogo" />
      <SeriesHeader series={series} />
      <CatalogGrid clusters={editions} from={`/series/${seriesKey}`} />
    </main>
  )
}

export async function generateStaticParams() {
  return allSeriesKeys().map(seriesKey => ({ seriesKey }))
}

export async function generateMetadata({ params }: Props) {
  const { seriesKey } = await params
  const series = seriesByKey(seriesKey)
  if (!series) return {}
  const edLabel = series.editionCount === 1 ? 'edición' : 'ediciones'
  const tomoLabel = series.itemCount === 1 ? 'tomo' : 'tomos'
  return {
    title: `${series.seriesDisplay} — PandaWatch`,
    description: `${series.editionCount} ${edLabel} · ${series.itemCount} ${tomoLabel}`,
    openGraph: {
      images: series.cover.imageUrl ? [series.cover.imageUrl] : [],
    },
  }
}
