import { describe, it, expect } from 'vitest'
import { filterClusters, sortClusters, paginate } from '@/lib/filters'
import type { Cluster, Item, FilterParams } from '@/lib/types'

// ---------------------------------------------------------------------------
// Fixture helpers
// ---------------------------------------------------------------------------

function makeItem(overrides: Partial<Item> = {}): Item {
  return {
    url: 'https://example.com/item',
    title: 'Test Manga 1',
    cluster_key: 'isbn:9780000000001',
    standardized_at: '2026-01-01T00:00:00Z',
    score: 50,
    signal_types: ['special_edition'],
    country: 'Japan',
    language: 'ja',
    publisher: 'Shueisha',
    product_type: 'manga',
    source_class: 'official',
    ...overrides,
  }
}

function makeCluster(overrides: Partial<Cluster> = {}): Cluster {
  const item = makeItem()
  return {
    clusterKey: item.cluster_key,
    slug: 'test-manga-1',
    canonical: item,
    items: [item],
    editionKey: 'test-manga-shueisha-special',
    editionDisplay: 'Test Manga Special Edition',
    seriesDisplay: 'Test Manga',
    volume: '1',
    volumeCount: 1,
    signalTypes: item.signal_types ?? [],
    countries: [item.country!],
    publishers: [item.publisher!],
    languages: [item.language!],
    minPrice: undefined,
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// A small fixture set used across tests
// ---------------------------------------------------------------------------

const berserkItem = makeItem({
  title: 'Berserk Deluxe 1',
  title_original: 'ベルセルク デラックス 1',
  series_display: 'Berserk',
  score: 120,
  signal_types: ['deluxe', 'hardcover'],
  country: 'Japan',
  language: 'ja',
  publisher: 'Dark Horse',
  cluster_key: 'isbn:9781506711980',
})

const berserkCluster = makeCluster({
  clusterKey: 'isbn:9781506711980',
  slug: 'berserk-darkhorse-deluxe-1',
  canonical: berserkItem,
  items: [berserkItem],
  editionKey: 'berserk-darkhorse-deluxe',
  seriesDisplay: 'Berserk',
  volume: '1',
  signalTypes: ['deluxe', 'hardcover'],
  countries: ['Japan'],
  publishers: ['Dark Horse'],
  languages: ['ja'],
})

const opBoxItem = makeItem({
  title: 'One Piece Box Set 1',
  series_display: 'One Piece',
  score: 90,
  signal_types: ['box_set'],
  country: 'France',
  language: 'fr',
  publisher: 'Glénat',
  cluster_key: 'isbn:9782344030011',
})

const opBoxCluster = makeCluster({
  clusterKey: 'isbn:9782344030011',
  slug: 'one-piece-glenat-boxset-1',
  canonical: opBoxItem,
  items: [opBoxItem],
  editionKey: 'one-piece-glenat-boxset',
  seriesDisplay: 'One Piece',
  volume: '1',
  signalTypes: ['box_set'],
  countries: ['France'],
  publishers: ['Glénat'],
  languages: ['fr'],
})

const demonSlayerItem = makeItem({
  title: 'Demon Slayer Limited 23',
  title_original: '鬼滅の刃 23 特装版',
  series_display: 'Demon Slayer',
  score: 75,
  signal_types: ['limited', 'bonus'],
  country: 'Spain',
  language: 'es',
  publisher: 'Panini',
  cluster_key: 'isbn:9788411009999',
  release_date: '2024-03-15',
})

const demonSlayerCluster = makeCluster({
  clusterKey: 'isbn:9788411009999',
  slug: 'demon-slayer-panini-limited-23',
  canonical: demonSlayerItem,
  items: [demonSlayerItem],
  editionKey: 'demon-slayer-panini-limited',
  seriesDisplay: 'Demon Slayer',
  volume: '23',
  signalTypes: ['limited', 'bonus'],
  countries: ['Spain'],
  publishers: ['Panini'],
  languages: ['es'],
})

const regularItem = makeItem({
  title: 'Generic Manga 5',
  series_display: 'Generic Manga',
  score: 20,
  signal_types: [],
  country: 'Italy',
  language: 'it',
  publisher: 'Star Comics',
  cluster_key: 'isbn:9788869209999',
  release_date: '2022-06-01',
})

const regularCluster = makeCluster({
  clusterKey: 'isbn:9788869209999',
  slug: 'generic-manga-star-5',
  canonical: regularItem,
  items: [regularItem],
  editionKey: 'generic-manga-star',
  seriesDisplay: 'Generic Manga',
  volume: '5',
  signalTypes: [],
  countries: ['Italy'],
  publishers: ['Star Comics'],
  languages: ['it'],
})

const noDateItem = makeItem({
  title: 'Obscure Artbook',
  score: 60,
  signal_types: ['artbook'],
  country: 'Japan',
  language: 'ja',
  publisher: 'Hakusensha',
  cluster_key: 'isbn:9784592000001',
  release_date: undefined,
})

const noDateCluster = makeCluster({
  clusterKey: 'isbn:9784592000001',
  slug: 'obscure-artbook',
  canonical: noDateItem,
  items: [noDateItem],
  signalTypes: ['artbook'],
  countries: ['Japan'],
  publishers: ['Hakusensha'],
  languages: ['ja'],
})

const ALL_CLUSTERS = [berserkCluster, opBoxCluster, demonSlayerCluster, regularCluster, noDateCluster]

const baseParams: FilterParams = {
  sort: 'score_desc',
  page: 1,
}

// ---------------------------------------------------------------------------
// filterClusters
// ---------------------------------------------------------------------------

describe('filterClusters', () => {
  it('returns all clusters when no params given', () => {
    const result = filterClusters(ALL_CLUSTERS, baseParams)
    expect(result).toHaveLength(ALL_CLUSTERS.length)
  })

  it('filters by q — case-insensitive substring on title', () => {
    const result = filterClusters(ALL_CLUSTERS, { ...baseParams, q: 'berserk' })
    expect(result).toHaveLength(1)
    expect(result[0].slug).toBe('berserk-darkhorse-deluxe-1')
  })

  it('filters by q — also matches title_original', () => {
    // 鬼滅の刃 is in demonSlayerItem.title_original
    const result = filterClusters(ALL_CLUSTERS, { ...baseParams, q: '鬼滅の刃' })
    expect(result).toHaveLength(1)
    expect(result[0].slug).toBe('demon-slayer-panini-limited-23')
  })

  it('filters by q — also matches series_display', () => {
    const result = filterClusters(ALL_CLUSTERS, { ...baseParams, q: 'one piece' })
    expect(result).toHaveLength(1)
    expect(result[0].slug).toBe('one-piece-glenat-boxset-1')
  })

  it('filters by country — ANY match (cluster with matching country passes)', () => {
    const result = filterClusters(ALL_CLUSTERS, { ...baseParams, country: ['France'] })
    expect(result).toHaveLength(1)
    expect(result[0].slug).toBe('one-piece-glenat-boxset-1')
  })

  it('filters by signal_types — ALL must be present (cluster missing one fails)', () => {
    // berserkCluster has ['deluxe','hardcover']; opBoxCluster has ['box_set']
    const result = filterClusters(ALL_CLUSTERS, { ...baseParams, signal_types: ['deluxe', 'hardcover'] })
    expect(result).toHaveLength(1)
    expect(result[0].slug).toBe('berserk-darkhorse-deluxe-1')
  })

  it('filters by min_score', () => {
    const result = filterClusters(ALL_CLUSTERS, { ...baseParams, min_score: 80 })
    // berserk (120) and opBox (90) pass; rest are below 80
    expect(result).toHaveLength(2)
    expect(result.map(c => c.slug).sort()).toEqual(
      ['berserk-darkhorse-deluxe-1', 'one-piece-glenat-boxset-1'].sort()
    )
  })

  it('only_limited=true — cluster with no limited signal excluded', () => {
    const result = filterClusters(
      [regularCluster],
      { ...baseParams, only_limited: true }
    )
    expect(result).toHaveLength(0)
  })

  it('only_limited=true — cluster with limited signal included', () => {
    const result = filterClusters(
      [demonSlayerCluster],
      { ...baseParams, only_limited: true }
    )
    expect(result).toHaveLength(1)
    expect(result[0].slug).toBe('demon-slayer-panini-limited-23')
  })
})

// ---------------------------------------------------------------------------
// sortClusters
// ---------------------------------------------------------------------------

describe('sortClusters', () => {
  it('score_desc puts highest score first', () => {
    const result = sortClusters(ALL_CLUSTERS, 'score_desc')
    expect(result[0].canonical.score).toBe(120) // berserk
    expect(result[result.length - 1].canonical.score).toBe(20) // regular
  })

  it('score_asc puts lowest score first', () => {
    const result = sortClusters(ALL_CLUSTERS, 'score_asc')
    expect(result[0].canonical.score).toBe(20) // regular
    expect(result[result.length - 1].canonical.score).toBe(120) // berserk
  })

  it('date_desc puts most recent first; items without date go last', () => {
    const result = sortClusters(ALL_CLUSTERS, 'date_desc')
    // demonSlayer 2024-03-15, regular 2022-06-01, others no date
    expect(result[0].canonical.release_date).toBe('2024-03-15')
    expect(result[1].canonical.release_date).toBe('2022-06-01')
    // remaining items have no release_date — they go to the end
    const tail = result.slice(2)
    expect(tail.every(c => !c.canonical.release_date)).toBe(true)
  })

  it('title_asc is alphabetical', () => {
    const result = sortClusters(ALL_CLUSTERS, 'title_asc')
    const titles = result.map(c => c.canonical.title)
    expect(titles).toEqual([...titles].sort((a, b) => a.localeCompare(b)))
  })
})

// ---------------------------------------------------------------------------
// paginate
// ---------------------------------------------------------------------------

describe('paginate', () => {
  const items = Array.from({ length: 150 }, (_, i) =>
    makeCluster({
      clusterKey: `isbn:97800000${String(i).padStart(5, '0')}`,
      slug: `item-${i}`,
    })
  )

  it('page=1 returns first pageSize items', () => {
    const result = paginate(items, 1, 60)
    expect(result.items).toHaveLength(60)
    expect(result.items[0].slug).toBe('item-0')
    expect(result.items[59].slug).toBe('item-59')
  })

  it('page=2 returns items 61–120 for pageSize=60', () => {
    const result = paginate(items, 2, 60)
    expect(result.items).toHaveLength(60)
    expect(result.items[0].slug).toBe('item-60')
    expect(result.items[59].slug).toBe('item-119')
  })

  it('returns correct total and pages counts', () => {
    const result = paginate(items, 1, 60)
    expect(result.total).toBe(150)
    expect(result.pages).toBe(3)
  })

  it('clamps out-of-range page to 1', () => {
    const result = paginate(items, 0, 60)
    expect(result.page).toBe(1)
    expect(result.items[0].slug).toBe('item-0')
  })
})
