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

function buildCluster(items: Item[]): Cluster {
  const sorted = [...items].sort((a, b) => (b.score || 0) - (a.score || 0))
  const canonical = sorted[0]
  const volumes = new Set(items.map(i => i.volume).filter(Boolean))

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
    countries: [...new Set(items.map(i => i.country).filter((c): c is string => Boolean(c)))],
    publishers: [...new Set(items.map(i => i.publisher).filter((p): p is string => Boolean(p)))],
    languages: [...new Set(items.map(i => i.language).filter((l): l is string => Boolean(l)))],
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

export function buildFacets(clusters: Cluster[]): Facets {
  const count = (values: string[]): { value: string; count: number }[] => {
    const map = new Map<string, number>()
    for (const v of values) map.set(v, (map.get(v) || 0) + 1)
    return Array.from(map.entries())
      .map(([value, count]) => ({ value, count }))
      .sort((a, b) => b.count - a.count)
  }

  const scores = clusters.map(c => c.canonical.score || 0)

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
    scoreRange: {
      min: scores.length ? Math.min(...scores) : 0,
      max: scores.length ? Math.max(...scores) : 0,
    },
  }
}
