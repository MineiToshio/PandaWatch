import type { MetadataRoute } from 'next'
import { absoluteUrl, seriesPath, editionPath, itemPath } from '@/lib/seo'
import { sitemapSeries, sitemapEditions, sitemapItems } from '@/lib/data'

/**
 * sitemap.xml (FRD-008 FR-3).
 *
 * Single file: the standardized corpus (series + editions + items) is well under the
 * 50,000-URL / 50 MB sitemap limit. When it approaches that ceiling, split via
 * `generateSitemaps()` returning one segment per entity (core/series/edition/item).
 *
 * All URLs derive from the data layer — no hand-maintained lists. Las claves van
 * percent-encoded (un <loc> con caracteres crudos no-ASCII es inválido) y cada
 * entrada lleva lastModified (max standardized_at/detected_at del cluster) para
 * que los crawlers prioricen re-crawl de lo que cambió con el delta diario.
 */
export default function sitemap(): MetadataRoute.Sitemap {
  const home: MetadataRoute.Sitemap = [
    { url: absoluteUrl('/'), changeFrequency: 'daily', priority: 1 },
  ]

  const series: MetadataRoute.Sitemap = sitemapSeries().map(({ seriesKey, lastMod }) => ({
    url: absoluteUrl(seriesPath(seriesKey)),
    ...(lastMod && { lastModified: lastMod }),
    changeFrequency: 'weekly',
    priority: 0.8,
  }))

  const editions: MetadataRoute.Sitemap = sitemapEditions().map(({ editionKey, lastMod }) => ({
    url: absoluteUrl(editionPath(editionKey)),
    ...(lastMod && { lastModified: lastMod }),
    changeFrequency: 'weekly',
    priority: 0.7,
  }))

  const items: MetadataRoute.Sitemap = sitemapItems().map(({ slug, lastMod }) => ({
    url: absoluteUrl(itemPath(slug)),
    ...(lastMod && { lastModified: lastMod }),
    changeFrequency: 'monthly',
    priority: 0.6,
  }))

  return [...home, ...series, ...editions, ...items]
}
