/**
 * schema.org JSON-LD builders (FRD-008 FR-8).
 *
 * Structured facts are what search engines turn into rich results and what LLM answer
 * engines extract most reliably — this is the highest-leverage discoverability surface.
 */
import { absoluteUrl, seriesPath, editionPath, itemPath } from '@/lib/seo'
import { coverImage } from '@/lib/data'
import { itemDescription, editionDescription, seriesDescription } from '@/lib/descriptions'
import type { Cluster, Item, Series } from '@/lib/types'

function imageUrl(c: Pick<Item, 'images'>): string | undefined {
  const { url, local } = coverImage(c)
  if (url) return url
  if (local) return absoluteUrl(`/images/${local}`)
  return undefined
}

export function itemJsonLd(cluster: Cluster, slug: string) {
  const c = cluster.canonical
  const url = absoluteUrl(itemPath(slug))

  return {
    '@context': 'https://schema.org',
    '@type': c.isbn ? ['Product', 'Book'] : 'Product',
    name: c.title,
    description: itemDescription(cluster),
    url,
    ...(imageUrl(c) && { image: imageUrl(c) }),
    // Sin bookFormat: no hay evidencia confiable del formato físico y declarar
    // Hardcover para todo item con ISBN era structured data falso.
    ...(c.isbn && { isbn: c.isbn }),
    ...(c.author && { author: { '@type': 'Person', name: c.author } }),
    ...(c.publisher && { publisher: { '@type': 'Organization', name: c.publisher } }),
    ...(c.release_date && { datePublished: c.release_date }),
    ...(c.language && { inLanguage: c.language }),
  }
}

export function editionJsonLd(
  cluster: Cluster,
  clusters: Cluster[],
  editionKey: string,
  totalVolumes: number,
  signalTypes: string[],
) {
  return {
    '@context': 'https://schema.org',
    '@type': 'CollectionPage',
    name: cluster.editionDisplay ?? cluster.seriesDisplay ?? editionKey,
    description: editionDescription(cluster, totalVolumes, signalTypes),
    url: absoluteUrl(editionPath(editionKey)),
    mainEntity: {
      '@type': 'ItemList',
      numberOfItems: clusters.length,
      itemListElement: clusters.map((v, i) => ({
        '@type': 'ListItem',
        position: i + 1,
        name: v.canonical.title,
        url: absoluteUrl(itemPath(v.slug)),
      })),
    },
  }
}

export function seriesJsonLd(series: Series, editions: Cluster[], seriesKey: string) {
  return {
    '@context': 'https://schema.org',
    '@type': 'CollectionPage',
    name: series.seriesDisplay,
    description: seriesDescription(series),
    url: absoluteUrl(seriesPath(seriesKey)),
    mainEntity: {
      '@type': 'ItemList',
      numberOfItems: editions.length,
      itemListElement: editions.map((e, i) => ({
        '@type': 'ListItem',
        position: i + 1,
        name: e.editionDisplay ?? e.canonical.title,
        url: e.editionKey
          ? absoluteUrl(editionPath(e.editionKey))
          : absoluteUrl(itemPath(e.slug)),
      })),
    },
  }
}

export function breadcrumbJsonLd(trail: { name: string; path: string }[]) {
  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: trail.map((t, i) => ({
      '@type': 'ListItem',
      position: i + 1,
      name: t.name,
      item: absoluteUrl(t.path),
    })),
  }
}

export function websiteJsonLd() {
  return {
    '@context': 'https://schema.org',
    '@type': 'WebSite',
    name: 'PandaWatch',
    description:
      'Tracker de ediciones especiales de manga: deluxe, box sets, limited editions, artbooks y más.',
    url: absoluteUrl('/'),
    potentialAction: {
      '@type': 'SearchAction',
      target: { '@type': 'EntryPoint', urlTemplate: absoluteUrl('/?q={query}') },
      'query-input': 'required name=query',
    },
  }
}

export function organizationJsonLd() {
  return {
    '@context': 'https://schema.org',
    '@type': 'Organization',
    name: 'PandaWatch',
    url: absoluteUrl('/'),
    logo: absoluteUrl('/icon-512.png'),
  }
}
