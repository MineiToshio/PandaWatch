import type { Cluster, FilterParams, SortKey, Item } from './types'
import { sortableDate } from './format'

/**
 * Normalización de texto para búsqueda (determinista, sin LLM):
 * lowercase + NFD + quita diacríticos combinantes. El CJK queda intacto (no
 * lleva marcas combinantes), así que el match por substring sigue funcionando.
 * Ej.: "Pokémon" → "pokemon", "Japón" → "japon", "L'Attaque" → "l'attaque".
 * Fuente ÚNICA de normalización — la comparten searchText (data layer) y el query.
 */
export function normalize(s: string): string {
  return s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
}

/** Sólo dígitos (y X del dígito de control ISBN-10), en minúscula. */
function isbnDigits(s?: string | null): string {
  return s ? s.replace(/[^0-9xX]/g, '').toLowerCase() : ''
}

/**
 * Texto buscable normalizado de un cluster. Une el nombre OFICIAL del título y
 * sus variantes, la serie, TODAS las editoriales del cluster y los ISBN (sin
 * guiones). NO transforma el título para display — es sólo un índice de búsqueda
 * (política de títulos 2026-06-12). Se precomputa una vez por cluster en el data
 * layer (buildCluster) y se reusa como fallback acá para clusters de fixtures.
 */
export function buildSearchText(
  canonical: Pick<Item, 'title' | 'title_original' | 'series_display' | 'isbn'>,
  publishers: string[] = [],
  isbns: (string | undefined)[] = [],
): string {
  const parts = [
    canonical.title,
    canonical.title_original,
    canonical.series_display,
    ...publishers,
    ...[canonical.isbn, ...isbns].map(isbnDigits).filter(Boolean),
  ].filter(Boolean) as string[]
  return normalize(parts.join(' '))
}

/**
 * Tokeniza el query en términos AND (todos deben matchear). Un token que parece
 * ISBN (10-13 dígitos con o sin guiones/espacios) se colapsa a dígitos para
 * empatar con el ISBN normalizado del searchText.
 */
function queryTokens(q: string): string[] {
  return normalize(q)
    .split(/\s+/)
    .filter(Boolean)
    .map(tok => {
      const digits = tok.replace(/-/g, '')
      return /^\d{10,13}$/.test(digits) ? digits : tok
    })
}

const LIMITED_SIGNALS = new Set([
  'limited',
  'special_edition',
  'collector',
  'lore_edition',
  'variant_cover',
  'artbook',
  'kanzenban',
  'deluxe',
  'box_set',
  'retailer_exclusive',
])

const SORT_KEYS: ReadonlySet<string> = new Set([
  'date_desc', 'date_asc', 'title_asc', 'title_desc',
] satisfies SortKey[])

export function parseFilterParams(
  params: Record<string, string | string[]>
): FilterParams {
  const getArr = (key: string): string[] | undefined => {
    const v = params[key]
    if (!v) return undefined
    return Array.isArray(v) ? v : [v]
  }
  // Next entrega los searchParams repetidos (?q=a&q=b) como string[] — para los
  // params escalares nos quedamos con el primero en vez de asumir string.
  const getStr = (key: string): string | undefined => {
    const v = params[key]
    return Array.isArray(v) ? v[0] : v
  }

  const rawSort = getStr('sort') ?? ''
  const rawPage = Number(getStr('page'))

  return {
    q: getStr('q'),
    country: getArr('country'),
    language: getArr('language'),
    publisher: getArr('publisher'),
    product_type: getArr('product_type'),
    source_class: getArr('source_class'),
    signal_types: getArr('signal_types'),
    rarity: getArr('rarity'),
    only_limited: getStr('only_limited') === 'true',
    sort: SORT_KEYS.has(rawSort) ? (rawSort as SortKey) : 'date_desc',
    page: Number.isInteger(rawPage) && rawPage > 0 ? rawPage : 1,
  }
}

export function filterClusters(
  clusters: Cluster[],
  params: FilterParams,
  // series_key → nombres de la serie en lowercase (lib/data.ts
  // aliasSearchIndex()). El title es el nombre OFICIAL de la edición (no se
  // renombra ni traduce); los aliases hacen que "demon slayer", "kimetsu no
  // yaiba" y "guardianes de la noche" devuelvan los mismos resultados.
  aliasIndex: Record<string, string> = {}
): Cluster[] {
  return clusters.filter(c => {
    const item = c.canonical

    // Full-text search: acentos normalizados + multi-token AND (todos los
    // tokens deben aparecer). El searchText normalizado se precomputa por
    // cluster en el data layer (buildCluster); fallback para clusters de
    // fixtures sin searchText. El aliasIndex ya viene normalizado (data.ts).
    if (params.q) {
      const tokens = queryTokens(params.q)
      if (tokens.length) {
        const base =
          c.searchText ??
          buildSearchText(item, c.publishers, c.items.map(i => i.isbn))
        const alias = item.series_key ? aliasIndex[item.series_key] : undefined
        const hay = alias ? `${base} ${alias}` : base
        if (!tokens.every(t => hay.includes(t))) return false
      }
    }

    // Array filters (ANY match)
    if (params.country?.length && !params.country.some(v => c.countries.includes(v)))
      return false
    if (params.language?.length && !params.language.some(v => c.languages.includes(v)))
      return false
    if (params.publisher?.length && !params.publisher.some(v => c.publishers.includes(v)))
      return false

    if (params.product_type?.length) {
      const types = c.items.map(i => i.product_type).filter(Boolean)
      if (!params.product_type.some(v => types.includes(v))) return false
    }

    if (params.source_class?.length) {
      const classes = c.items.map(i => i.source_class).filter(Boolean)
      if (!params.source_class.some(v => classes.includes(v))) return false
    }

    // Signal types (ALL must be present)
    if (params.signal_types?.length) {
      if (!params.signal_types.every(s => c.signalTypes.includes(s))) return false
    }

    // Rarity (ANY match)
    if (params.rarity?.length && !params.rarity.includes(item.rarity ?? ''))
      return false

    // Only limited
    if (params.only_limited && !c.signalTypes.some(s => LIMITED_SIGNALS.has(s)))
      return false

    return true
  })
}

export function sortClusters(
  clusters: Cluster[],
  sort: SortKey = 'date_desc'
): Cluster[] {
  return [...clusters].sort((a, b) => {
    switch (sort) {
      case 'date_desc': {
        const da = a.canonical.release_date || ''
        const db = b.canonical.release_date || ''
        if (!da && !db) return 0
        if (!da) return 1
        if (!db) return -1
        return sortableDate(db).localeCompare(sortableDate(da))
      }
      case 'date_asc': {
        const da = a.canonical.release_date || ''
        const db = b.canonical.release_date || ''
        if (!da && !db) return 0
        if (!da) return 1
        if (!db) return -1
        return sortableDate(da).localeCompare(sortableDate(db))
      }
      case 'title_asc':
        return (a.canonical.title || '').localeCompare(b.canonical.title || '')
      case 'title_desc':
        return (b.canonical.title || '').localeCompare(a.canonical.title || '')
      default:
        return 0
    }
  })
}

export function paginate<T>(items: T[], page: number, pageSize = 60) {
  const total = items.length
  const pages = Math.ceil(total / pageSize)
  const wanted = Number.isFinite(page) ? Math.trunc(page) : 1
  const safeP = Math.max(1, Math.min(wanted, pages || 1))
  const start = (safeP - 1) * pageSize
  return {
    items: items.slice(start, start + pageSize),
    total,
    pages,
    page: safeP,
  }
}
