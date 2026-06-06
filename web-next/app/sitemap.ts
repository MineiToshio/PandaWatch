import type { MetadataRoute } from 'next'
import { absoluteUrl } from '@/lib/seo'
import { allSeriesKeys, allEditionKeys, allSlugs } from '@/lib/data'

/**
 * sitemap.xml (FRD-008 FR-3).
 *
 * Single file: the standardized corpus (series + editions + items) is well under the
 * 50,000-URL / 50 MB sitemap limit. When it approaches that ceiling, split via
 * `generateSitemaps()` returning one segment per entity (core/series/edition/item).
 *
 * All URLs derive from the data layer — no hand-maintained lists.
 */
export default function sitemap(): MetadataRoute.Sitemap {
  const home: MetadataRoute.Sitemap = [
    { url: absoluteUrl('/'), changeFrequency: 'daily', priority: 1 },
  ]

  const series: MetadataRoute.Sitemap = allSeriesKeys().map(key => ({
    url: absoluteUrl(`/series/${key}`),
    changeFrequency: 'weekly',
    priority: 0.8,
  }))

  const editions: MetadataRoute.Sitemap = allEditionKeys().map(key => ({
    url: absoluteUrl(`/edition/${key}`),
    changeFrequency: 'weekly',
    priority: 0.7,
  }))

  const items: MetadataRoute.Sitemap = allSlugs().map(slug => ({
    url: absoluteUrl(`/item/${slug}`),
    changeFrequency: 'monthly',
    priority: 0.6,
  }))

  return [...home, ...series, ...editions, ...items]
}
