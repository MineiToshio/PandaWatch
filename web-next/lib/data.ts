import fs from 'fs'
import path from 'path'
import type { Item, Cluster, Facets, Series } from './types'
import { buildSearchText, normalize } from './filters'
import { editionSlugRank, signalRank } from './vocab'

// Path relative to web-next/ (process.cwd() in Next.js). Overridable via env
// for deploys where the data lives elsewhere (pending: migración a DB).
const ITEMS_PATH =
  process.env.ITEMS_PATH ?? path.join(process.cwd(), '..', 'data', 'items.jsonl')

// Vista de búsqueda de aliases ({series_key: [nombres…]}), generada desde
// series_aliases.yml por scripts/export_series_aliases.py (la regenera cada
// build_web.py). Vive junto al items.jsonl por defecto; ALIASES_PATH permite
// apuntarla a otra ubicación en deploys (coherente con ITEMS_PATH).
const ALIASES_PATH =
  process.env.ALIASES_PATH ??
  path.join(path.dirname(ITEMS_PATH), 'series_aliases.json')

function readRawItems(): Item[] {
  let raw: string
  try {
    raw = fs.readFileSync(ITEMS_PATH, 'utf-8')
  } catch {
    throw new Error(
      `items.jsonl not found at ${ITEMS_PATH} — run the scraper first ` +
      `(or set ITEMS_PATH to the corpus location)`
    )
  }
  let malformed = 0
  let noCluster = 0
  const items = raw
    .split('\n')
    .filter(Boolean)
    .flatMap(line => {
      try {
        return [JSON.parse(line) as Item]
      } catch {
        malformed++
        return []
      }
    })
    .filter(item => {
      // Una fila sin cluster_key agruparía todos los registros rotos bajo un
      // cluster fantasma `undefined` — se descarta con warn, no en silencio.
      if (!item.cluster_key) {
        noCluster++
        return false
      }
      return Boolean(item.standardized_at)
    })
  if (malformed) console.warn(`[data] items.jsonl: ${malformed} malformed lines skipped`)
  if (noCluster) console.warn(`[data] items.jsonl: ${noCluster} rows without cluster_key skipped`)
  return items
}

// Volúmenes-rango ("1-3" de un cofre): parseFloat("1-3") = 1, así que un rango
// empata con su primer tomo. Se desempata por el extremo final del rango
// (el tomo suelto "1" va antes que el cofre "1-3").
function volumeBounds(v: string): [number, number] | null {
  const range = v.match(/^(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)$/)
  if (range) return [parseFloat(range[1]), parseFloat(range[2])]
  const num = parseFloat(v)
  return isNaN(num) ? null : [num, num]
}

export function compareVolumes(a?: string, b?: string): number {
  if (!a && !b) return 0
  if (!a) return 1  // no volume → end
  if (!b) return -1
  const ba = volumeBounds(a)
  const bb = volumeBounds(b)
  if (ba && bb) return ba[0] - bb[0] || ba[1] - bb[1]
  return a.localeCompare(b)
}

// Rango de kind para desempate dentro del mismo volumen (gotcha #60).
// Orden global: regular(0) → variant(1) → special/limited(2) →
// deluxe/kanzenban(3) → artbook/fanbook(4) → boxset(5) → desconocido(10).
// Vocabulario (rank por slug/señal) en lib/vocab.ts — fuente única (auditoría #12).
function kindRank(c: Cluster): number {
  // Tier 1: cluster_key lmc → kind en posición 2 ("lmc:ID:kind:vol")
  if (c.clusterKey.startsWith('lmc:')) {
    const parts = c.clusterKey.split(':')
    if (parts.length >= 3) {
      const r = editionSlugRank(parts[2])
      if (r !== undefined) return r
    }
  }
  // Tier 2: edition_key slug → penúltimo segmento antes del país
  if (c.editionKey) {
    const parts = c.editionKey.split('-')
    if (parts.length >= 2) {
      const r = editionSlugRank(parts[parts.length - 2])
      if (r !== undefined) return r
    }
  }
  // Tier 3: signal_types
  const r = signalRank(c.signalTypes)
  return r !== undefined ? r : 10
}

// Portada canónica de un item: `images[0]` es la ÚNICA fuente de verdad (los
// campos top-level image_url/image_local fueron eliminados, 2026-06-09). Ver
// CLAUDE.md / docs/reference/images.md.
export function coverImage(
  item: Pick<Item, 'images'>,
): { url?: string; local?: string } {
  const first = (item.images ?? []).find(im => im && im.url)
  return first ? { url: first.url, local: first.local } : {}
}

// Completitud de un item: prioriza el que tiene más metadata para elegir el
// representante canónico de un cluster (reemplaza la antigua selección por score).
function completeness(item: Item): number {
  return (item.isbn ? 100 : 0) + (item.images?.length ? 10 : 0)
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

  const publishers = collect('publisher')

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
    publishers,
    languages: collect('language'),
    // Índice de búsqueda normalizado (una vez por cluster, no por request —
    // ver auditoría #6). Incluye editoriales + ISBN (búsqueda por editorial/ISBN,
    // auditoría #1). Los aliases de serie se unen en filterClusters (viven en un
    // JSON con mtime propio). El title NUNCA se transforma para display.
    searchText: buildSearchText(canonical, publishers, items.map(i => i.isbn)),
    // minPrice eliminado: precios fuera del pipeline (decisión 2026-06-11,
    // architecture.md — catálogo de descubrimiento, no tracker de precios).
  }
}

// Cache invalidado por mtime del JSONL: en build/prod se parsea una sola vez
// por proceso; en dev se re-parsea sólo cuando el archivo cambió (sin esto,
// cada request de dev re-leía y re-agrupaba el corpus completo).
// Los Maps evitan scans O(n) por página durante generateStaticParams
// (~19k páginas × lookup lineal de ~9.5k clusters).
type DataCache = {
  mtimeMs: number
  clusters: Cluster[]
  bySlug: Map<string, Cluster>
  byEdition: Map<string, Cluster[]>
  // Índice serie→clusters (mismo patrón que byEdition). Evita el scan lineal
  // de loadSeriesEditions/seriesCache por cada página de serie (auditoría #23).
  bySeries: Map<string, Cluster[]>
  // Facets globales cacheados: idénticos entre requests mientras el corpus no
  // cambia (se invalidan con el mtime, igual que bySlug). La home los recalculaba
  // por request bajo force-dynamic (auditoría #6).
  facets: Facets
}

let _cache: DataCache | null = null

// Índice de búsqueda por alias: series_key → todos los nombres de la serie
// (canónico + traducciones/romanizaciones) en lowercase. Permite que la
// búsqueda encuentre "Guardianes de la Noche 8" tecleando "demon slayer" o
// "kimetsu no yaiba": el title de cada item es el nombre OFICIAL de la
// edición y NUNCA se renombra (política de títulos 2026-06-12).
// Cache por mtime, mismo patrón que dataCache(). Si el JSON no existe
// todavía, la búsqueda funciona sin aliases (índice vacío).
type AliasCache = { mtimeMs: number; index: Record<string, string> }
let _aliasCache: AliasCache | null = null

export function aliasSearchIndex(): Record<string, string> {
  let mtimeMs = 0
  try {
    mtimeMs = fs.statSync(ALIASES_PATH).mtimeMs
  } catch {
    return {}
  }
  if (_aliasCache && _aliasCache.mtimeMs === mtimeMs) return _aliasCache.index
  let index: Record<string, string> = {}
  try {
    const raw = JSON.parse(fs.readFileSync(ALIASES_PATH, 'utf-8')) as Record<string, string[]>
    // Normalizado (misma función que el query y el searchText) para que la
    // búsqueda por alias sea insensible a acentos igual que el resto.
    index = Object.fromEntries(
      Object.entries(raw).map(([k, names]) => [k, normalize(names.join(' '))])
    )
  } catch {
    console.warn(`[data] series_aliases.json ilegible en ${ALIASES_PATH} — búsqueda sin aliases`)
  }
  _aliasCache = { mtimeMs, index }
  return index
}

function dataCache(): DataCache {
  let mtimeMs = 0
  try {
    mtimeMs = fs.statSync(ITEMS_PATH).mtimeMs
  } catch {
    // readRawItems() reporta el error descriptivo
  }
  if (_cache && _cache.mtimeMs === mtimeMs) return _cache

  const items = readRawItems()
  const groups = new Map<string, Item[]>()
  for (const item of items) {
    const key = item.cluster_key
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(item)
  }

  const clusters = Array.from(groups.values()).map(buildCluster)

  const bySlug = new Map<string, Cluster>()
  for (const c of clusters) {
    if (!c.slug) continue
    if (bySlug.has(c.slug)) {
      // La unicidad slug↔cluster es una invariante del pipeline Python
      // (FRD-006 FR-2); si se rompe upstream, acá se detecta en vez de
      // hacer shadowing silencioso de la ficha.
      console.warn(`[data] duplicate slug "${c.slug}" — cluster ${c.clusterKey} shadowed`)
      continue
    }
    bySlug.set(c.slug, c)
  }

  const byEdition = new Map<string, Cluster[]>()
  for (const c of clusters) {
    if (!c.editionKey) continue
    if (!byEdition.has(c.editionKey)) byEdition.set(c.editionKey, [])
    byEdition.get(c.editionKey)!.push(c)
  }
  for (const list of byEdition.values()) {
    list.sort((a, b) => compareVolumes(a.volume, b.volume) || kindRank(a) - kindRank(b))
  }

  const bySeries = new Map<string, Cluster[]>()
  for (const c of clusters) {
    const key = c.canonical.series_key
    if (!key) continue
    if (!bySeries.has(key)) bySeries.set(key, [])
    bySeries.get(key)!.push(c)
  }

  _cache = { mtimeMs, clusters, bySlug, byEdition, bySeries, facets: buildFacets(clusters) }
  _seriesCache = null
  return _cache
}

export function loadClusters(): Cluster[] {
  return dataCache().clusters
}

/** Facets globales cacheados (invalidados por mtime). Ver auditoría #6. */
export function loadFacets(): Facets {
  return dataCache().facets
}

export function loadEditionClusters(editionKey: string): Cluster[] {
  return dataCache().byEdition.get(editionKey) ?? []
}

export function clusterBySlug(slug: string): Cluster | null {
  return dataCache().bySlug.get(slug) ?? null
}

export function allEditionKeys(): string[] {
  return [...dataCache().byEdition.keys()]
}

export function allSlugs(): string[] {
  return [...dataCache().bySlug.keys()]
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

      // Promote to canonical if this cluster's item is more complete (ISBN/image)
      if (completeness(cluster.canonical) > completeness(entry.canonical)) {
        entry.canonical = cluster.canonical
        entry.slug = cluster.slug
        entry.volume = cluster.volume  // mantener portada y volumen coherentes
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

// ─── Series (obra) aggregates ─────────────────────────────────────────────────

const RARITY_ORDER = ['common', 'rare', 'super_rare', 'ultra_rare'] as const

function buildSeries(seriesKey: string, clusters: Cluster[]): Series {
  const editionKeys = new Set<string>()
  const clusterKeys = new Set<string>()
  const countries = new Set<string>()
  const publishers = new Set<string>()
  const signalTypes = new Set<string>()
  let cover: Series['cover'] = {}
  let bestCover = -1
  let topRarityIdx = -1

  for (const c of clusters) {
    if (c.editionKey) editionKeys.add(c.editionKey)
    clusterKeys.add(c.clusterKey)
    c.countries.forEach(v => countries.add(v))
    c.publishers.forEach(v => publishers.add(v))
    c.signalTypes.forEach(v => signalTypes.add(v))

    const it = c.canonical
    const score = completeness(it)
    const cov = coverImage(it)
    if ((cov.local || cov.url) && score > bestCover) {
      bestCover = score
      cover = { imageLocal: cov.local, imageUrl: cov.url }
    }
    const ri = it.rarity ? RARITY_ORDER.indexOf(it.rarity as typeof RARITY_ORDER[number]) : -1
    if (ri > topRarityIdx) topRarityIdx = ri
  }

  return {
    seriesKey,
    seriesDisplay:
      clusters[0].seriesDisplay ||
      clusters[0].canonical.series_display ||
      seriesKey,
    cover,
    editionCount: editionKeys.size,
    itemCount: clusterKeys.size,
    countries: [...countries],
    publishers: [...publishers],
    signalTypes: [...signalTypes],
    topRarity: topRarityIdx >= 0 ? RARITY_ORDER[topRarityIdx] : undefined,
  }
}

// Invalidado junto con el cache principal (dataCache() lo resetea al cambiar
// el mtime del JSONL).
let _seriesCache: { series: Series[]; byKey: Map<string, Series> } | null = null

function seriesCache(): { series: Series[]; byKey: Map<string, Series> } {
  const cache = dataCache() // resetea _seriesCache si el corpus cambió
  if (_seriesCache) return _seriesCache

  const collator = new Intl.Collator('es')
  const series = Array.from(cache.bySeries.entries())
    .map(([key, clusters]) => buildSeries(key, clusters))
    // FRD-007 FR-2 ranking — isolated comparator for easy retuning
    .sort((a, b) =>
      b.editionCount - a.editionCount ||
      b.itemCount - a.itemCount ||
      collator.compare(a.seriesDisplay, b.seriesDisplay)
    )

  _seriesCache = { series, byKey: new Map(series.map(s => [s.seriesKey, s])) }
  return _seriesCache
}

export function loadSeries(): Series[] {
  return seriesCache().series
}

export function seriesByKey(seriesKey: string): Series | null {
  return seriesCache().byKey.get(seriesKey) ?? null
}

export function loadSeriesEditions(seriesKey: string): Cluster[] {
  // Índice bySeries (auditoría #23): evita el scan lineal del corpus por cada
  // una de las ~3.7k páginas de serie en build.
  const clusters = dataCache().bySeries.get(seriesKey) ?? []
  return groupByEdition(clusters).sort(
    (a, b) =>
      b.volumeCount - a.volumeCount ||
      (a.canonical.title || '').localeCompare(b.canonical.title || '')
  )
}

export function allSeriesKeys(): string[] {
  return loadSeries().map(s => s.seriesKey)
}

/** Build and rank Series from an arbitrary subset of clusters (e.g. filtered results).
 *  Used by the catalog home to show context-relevant highlights. */
export function seriesFromClusters(clusters: Cluster[], limit = 12): Series[] {
  const bySeries = new Map<string, Cluster[]>()
  for (const c of clusters) {
    const key = c.canonical.series_key
    if (!key) continue
    if (!bySeries.has(key)) bySeries.set(key, [])
    bySeries.get(key)!.push(c)
  }
  const collator = new Intl.Collator('es')
  return Array.from(bySeries.entries())
    .map(([key, cls]) => buildSeries(key, cls))
    .filter(s => s.cover.imageLocal || s.cover.imageUrl)
    .sort((a, b) =>
      b.editionCount - a.editionCount ||
      b.itemCount - a.itemCount ||
      collator.compare(a.seriesDisplay, b.seriesDisplay)
    )
    .slice(0, limit)
}

// ─── Facets ───────────────────────────────────────────────────────────────────

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
    signalTypes: count(clusters.flatMap(c => c.signalTypes)),
  }
}

// ─── Sitemap helpers ──────────────────────────────────────────────────────────

/** Última actividad conocida de un cluster (para lastModified del sitemap). */
function clusterLastMod(c: Cluster): string | undefined {
  let max: string | undefined
  for (const it of c.items) {
    for (const d of [it.standardized_at, it.detected_at]) {
      if (d && (!max || d > max)) max = d
    }
  }
  return max
}

const maxDate = (a?: string, b?: string) =>
  !a ? b : !b ? a : a > b ? a : b

export function sitemapItems(): { slug: string; lastMod?: string }[] {
  return [...dataCache().bySlug.values()].map(c => ({
    slug: c.slug,
    lastMod: clusterLastMod(c),
  }))
}

export function sitemapEditions(): { editionKey: string; lastMod?: string }[] {
  return [...dataCache().byEdition.entries()].map(([editionKey, clusters]) => ({
    editionKey,
    lastMod: clusters.map(clusterLastMod).reduce(maxDate, undefined),
  }))
}

export function sitemapSeries(): { seriesKey: string; lastMod?: string }[] {
  const lastModBySeries = new Map<string, string | undefined>()
  for (const c of loadClusters()) {
    const key = c.canonical.series_key
    if (!key) continue
    lastModBySeries.set(key, maxDate(lastModBySeries.get(key), clusterLastMod(c)))
  }
  return allSeriesKeys().map(seriesKey => ({
    seriesKey,
    lastMod: lastModBySeries.get(seriesKey),
  }))
}
