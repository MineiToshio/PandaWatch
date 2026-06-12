import type { Cluster, FilterParams, SortKey } from './types'
import { sortableDate } from './format'

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

    // Full-text search
    if (params.q) {
      const q = params.q.toLowerCase()
      const searchable = [
        item.title,
        item.title_original,
        item.series_display,
        item.series_key ? aliasIndex[item.series_key] : undefined,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
      if (!searchable.includes(q)) return false
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
