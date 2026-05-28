import type { Cluster, FilterParams, SortKey, Facets } from './types'

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

export function parseFilterParams(
  params: Record<string, string | string[]>
): FilterParams {
  const getArr = (key: string): string[] | undefined => {
    const v = params[key]
    if (!v) return undefined
    return Array.isArray(v) ? v : [v]
  }

  return {
    q: params.q as string | undefined,
    country: getArr('country'),
    language: getArr('language'),
    publisher: getArr('publisher'),
    product_type: getArr('product_type'),
    source_class: getArr('source_class'),
    signal_types: getArr('signal_types'),
    min_score: params.min_score ? Number(params.min_score) : undefined,
    only_limited: params.only_limited === 'true',
    sort: (params.sort as SortKey) || 'score_desc',
    page: params.page ? Number(params.page) : 1,
  }
}

export function filterClusters(
  clusters: Cluster[],
  params: FilterParams
): Cluster[] {
  return clusters.filter(c => {
    const item = c.canonical

    // Full-text search
    if (params.q) {
      const q = params.q.toLowerCase()
      const searchable = [item.title, item.title_original, item.series_display]
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

    // Min score
    if (params.min_score && (item.score || 0) < params.min_score) return false

    // Only limited
    if (params.only_limited && !c.signalTypes.some(s => LIMITED_SIGNALS.has(s)))
      return false

    return true
  })
}

export function sortClusters(
  clusters: Cluster[],
  sort: SortKey = 'score_desc'
): Cluster[] {
  return [...clusters].sort((a, b) => {
    switch (sort) {
      case 'score_desc':
        return (b.canonical.score || 0) - (a.canonical.score || 0)
      case 'score_asc':
        return (a.canonical.score || 0) - (b.canonical.score || 0)
      case 'date_desc': {
        const da = a.canonical.release_date || ''
        const db = b.canonical.release_date || ''
        if (!da && !db) return 0
        if (!da) return 1
        if (!db) return -1
        return db.localeCompare(da)
      }
      case 'date_asc': {
        const da = a.canonical.release_date || ''
        const db = b.canonical.release_date || ''
        if (!da && !db) return 0
        if (!da) return 1
        if (!db) return -1
        return da.localeCompare(db)
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
  const safeP = Math.max(1, Math.min(page, pages || 1))
  const start = (safeP - 1) * pageSize
  return {
    items: items.slice(start, start + pageSize),
    total,
    pages,
    page: safeP,
  }
}
