/**
 * schema.org JSON-LD builders (FRD-008 FR-8).
 *
 * Structured facts are what search engines turn into rich results and what LLM answer
 * engines extract most reliably — this is the highest-leverage discoverability surface.
 */
import { absoluteUrl } from '@/lib/seo'
import { itemDescription, editionDescription, seriesDescription } from '@/lib/descriptions'
import type { Cluster, Item, Series } from '@/lib/types'

/** Best-effort country → ISO-4217 currency. Defaults to USD (logged as a gap upstream). */
const COUNTRY_CURRENCY: Record<string, string> = {
  Japan: 'JPY',
  Japón: 'JPY',
  USA: 'USD',
  'Estados Unidos': 'USD',
  'United States': 'USD',
  'Reino Unido': 'GBP',
  UK: 'GBP',
  España: 'EUR',
  Francia: 'EUR',
  France: 'EUR',
  Italia: 'EUR',
  Alemania: 'EUR',
  Germany: 'EUR',
  Brasil: 'BRL',
  Brazil: 'BRL',
  México: 'MXN',
  Argentina: 'ARS',
}

function currencyFor(country?: string): string {
  return (country && COUNTRY_CURRENCY[country]) || 'USD'
}

function priceValue(price?: string): string | null {
  if (!price) return null
  const n = price.replace(/[^0-9.,]/g, '').replace(/\.(?=\d{3}\b)/g, '').replace(',', '.')
  return parseFloat(n || '0') > 0 ? n : null
}

function availabilityFor(c: Item): string {
  if (c.stock_type === 'out_of_stock') return 'https://schema.org/OutOfStock'
  if (c.rarity === 'super_rare' || c.rarity === 'ultra_rare')
    return 'https://schema.org/LimitedAvailability'
  return 'https://schema.org/InStock'
}

function imageUrl(c: Pick<Item, 'image_url' | 'image_local'>): string | undefined {
  if (c.image_url) return c.image_url
  if (c.image_local) return absoluteUrl(`/images/${c.image_local}`)
  return undefined
}

export function itemJsonLd(cluster: Cluster, slug: string) {
  const c = cluster.canonical
  const url = absoluteUrl(`/item/${slug}`)
  const price = priceValue(c.price)

  return {
    '@context': 'https://schema.org',
    '@type': c.isbn ? ['Product', 'Book'] : 'Product',
    name: c.title,
    description: itemDescription(cluster),
    url,
    ...(imageUrl(c) && { image: imageUrl(c) }),
    ...(c.isbn && { isbn: c.isbn, bookFormat: 'https://schema.org/Hardcover' }),
    ...(c.author && { author: { '@type': 'Person', name: c.author } }),
    ...(c.publisher && { publisher: { '@type': 'Organization', name: c.publisher } }),
    ...(c.release_date && { datePublished: c.release_date }),
    ...(c.language && { inLanguage: c.language }),
    ...(price && {
      offers: {
        '@type': 'Offer',
        price,
        priceCurrency: currencyFor(c.country),
        availability: availabilityFor(c),
        ...(c.url && { url: c.url }),
      },
    }),
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
    url: absoluteUrl(`/edition/${editionKey}`),
    mainEntity: {
      '@type': 'ItemList',
      numberOfItems: clusters.length,
      itemListElement: clusters.map((v, i) => ({
        '@type': 'ListItem',
        position: i + 1,
        name: v.canonical.title,
        url: absoluteUrl(`/item/${v.slug}`),
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
    url: absoluteUrl(`/series/${seriesKey}`),
    mainEntity: {
      '@type': 'ItemList',
      numberOfItems: editions.length,
      itemListElement: editions.map((e, i) => ({
        '@type': 'ListItem',
        position: i + 1,
        name: e.editionDisplay ?? e.canonical.title,
        url: e.editionKey
          ? absoluteUrl(`/edition/${e.editionKey}`)
          : absoluteUrl(`/item/${e.slug}`),
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
