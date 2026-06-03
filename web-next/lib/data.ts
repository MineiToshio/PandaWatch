import fs from 'fs'
import path from 'path'
import type { Item, Cluster, Facets } from './types'

// Path relative to web-next/ (process.cwd() in Next.js)
const ITEMS_PATH = path.join(process.cwd(), '..', 'data', 'items.jsonl')

let _cache: Cluster[] | null = null

function readRawItems(): Item[] {
  const raw = fs.readFileSync(ITEMS_PATH, 'utf-8')
  return raw
    .split('\n')
    .filter(Boolean)
    .flatMap(line => {
      try {
        return [JSON.parse(line) as Item]
      } catch {
        return []
      }
    })
    .filter(item => Boolean(item.standardized_at))
}

function compareVolumes(a?: string, b?: string): number {
  if (!a && !b) return 0
  if (!a) return 1  // no volume → end
  if (!b) return -1
  const numA = parseFloat(a)
  const numB = parseFloat(b)
  if (!isNaN(numA) && !isNaN(numB)) return numA - numB
  return a.localeCompare(b)
}

function resolveMinPrice(items: Item[]): string | undefined {
  const prices = items
    .map(i => i.price)
    .filter((p): p is string => Boolean(p))
    .map(p => parseFloat(p.replace(/[^0-9.,]/g, '').replace(',', '.')))
    .filter(n => !isNaN(n))
  if (!prices.length) return undefined
  return String(Math.min(...prices))
}

// Completitud de un item: prioriza el que tiene más metadata para elegir el
// representante canónico de un cluster (reemplaza la antigua selección por
// score). Mismo criterio que el dedup del pipeline Python (ISBN > imagen > precio).
function completeness(item: Item): number {
  return (item.isbn ? 100 : 0) + (item.image_url ? 10 : 0) + (item.price ? 5 : 0)
}

function buildCluster(items: Item[]): Cluster {
  const sorted = [...items].sort((a, b) => completeness(b) - completeness(a))
  const canonical = sorted[0]
  const volumes = new Set(items.map(i => i.volume).filter(Boolean))

  // Modelo 1-fila-por-producto: country/publisher/language por-fuente viven en
  // `sources[]`. Para país/editorial/idioma del cluster unimos las filas + las
  // entradas de sources[] (si no, un producto multi-fuente perdería los países
  // de las fuentes hermanas, que ya no son filas separadas).
  const srcEntries = items.flatMap(i => i.sources || [])
  const collect = (key: 'country' | 'publisher' | 'language'): string[] => {
    const vals = [
      ...items.map(i => i[key]),
      ...srcEntries.map(s => s[key]),
    ].filter((v): v is string => Boolean(v))
    return [...new Set(vals)]
  }

  return {
    clusterKey: canonical.cluster_key,
    slug: canonical.slug || '',
    canonical,
    items,
    editionKey: canonical.edition_key,
    editionDisplay: canonical.edition_display,
    seriesDisplay: canonical.series_display,
    volume: canonical.volume,
    volumeCount: volumes.size || 1,
    signalTypes: [...new Set(items.flatMap(i => i.signal_types || []))],
    countries: collect('country'),
    publishers: collect('publisher'),
    languages: collect('language'),
    minPrice: resolveMinPrice(items),
  }
}

export function loadClusters(): Cluster[] {
  if (process.env.NODE_ENV === 'production' && _cache) return _cache

  const items = readRawItems()
  const groups = new Map<string, Item[]>()
  for (const item of items) {
    const key = item.cluster_key
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(item)
  }

  const clusters = Array.from(groups.values()).map(buildCluster)
  if (process.env.NODE_ENV === 'production') _cache = clusters
  return clusters
}

export function loadEditionClusters(editionKey: string): Cluster[] {
  return loadClusters()
    .filter(c => c.editionKey === editionKey)
    .sort((a, b) => compareVolumes(a.volume, b.volume))
}

export function clusterBySlug(slug: string): Cluster | null {
  return loadClusters().find(c => c.slug === slug) ?? null
}

export function allEditionKeys(): string[] {
  return [
    ...new Set(
      loadClusters()
        .map(c => c.editionKey)
        .filter((k): k is string => Boolean(k))
    ),
  ]
}

export function allSlugs(): string[] {
  return loadClusters()
    .map(c => c.slug)
    .filter((s): s is string => Boolean(s))
}

/**
 * Collapse clusters that share the same edition_key into a single representative
 * entry for the catalog home page.
 *
 * - Editions with N volumes → one card, volumeCount=N, links to /edition/[editionKey]
 * - Standalone clusters (no edition_key) → one card each, links to /item/[slug]
 *
 * Sort order is preserved: the position of an edition card in the result is
 * determined by where its first cluster appeared in the (already-sorted) input.
 */
export function groupByEdition(clusters: Cluster[]): Cluster[] {
  const result: Cluster[] = []
  const editionIndexMap = new Map<string, number>() // editionKey → index in result

  for (const cluster of clusters) {
    if (!cluster.editionKey) {
      // Standalone — keep as-is
      result.push(cluster)
      continue
    }

    const idx = editionIndexMap.get(cluster.editionKey)
    if (idx === undefined) {
      // First cluster for this edition — insert it (volumeCount = 1 for now)
      editionIndexMap.set(cluster.editionKey, result.length)
      result.push({ ...cluster, volumeCount: 1 })
    } else {
      // Another volume of the same edition — merge into the existing entry
      const entry = result[idx]
      entry.volumeCount += 1

      // Promote to canonical if this cluster's item is more complete (ISBN/image/price)
      if (completeness(cluster.canonical) > completeness(entry.canonical)) {
        entry.canonical = cluster.canonical
        entry.slug = cluster.slug
      }

      // Union all metadata arrays
      entry.signalTypes = [...new Set([...entry.signalTypes, ...cluster.signalTypes])]
      entry.countries   = [...new Set([...entry.countries,   ...cluster.countries])]
      entry.publishers  = [...new Set([...entry.publishers,  ...cluster.publishers])]
      entry.languages   = [...new Set([...entry.languages,   ...cluster.languages])]
    }
  }

  return result
}

export function buildFacets(clusters: Cluster[]): Facets {
  const count = (values: string[]): { value: string; count: number }[] => {
    const map = new Map<string, number>()
    for (const v of values) map.set(v, (map.get(v) || 0) + 1)
    return Array.from(map.entries())
      .map(([value, count]) => ({ value, count }))
      .sort((a, b) => b.count - a.count)
  }

  return {
    countries: count(clusters.flatMap(c => c.countries)),
    languages: count(clusters.flatMap(c => c.languages)),
    publishers: count(clusters.flatMap(c => c.publishers)),
    productTypes: count(
      clusters.flatMap(c =>
        c.items.map(i => i.product_type).filter((t): t is string => Boolean(t))
      )
    ),
    sourceClasses: count(
      clusters.flatMap(c =>
        c.items.map(i => i.source_class).filter((s): s is string => Boolean(s))
      )
    ),
    signalTypes: count(clusters.flatMap(c => c.signalTypes)),
  }
}
