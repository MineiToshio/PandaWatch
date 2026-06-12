import { describe, it, expect } from 'vitest'
import { compareVolumes, groupByEdition, buildFacets } from '@/lib/data'
import { dedupeImages, imageKey } from '@/lib/images'
import type { Cluster, Item } from '@/lib/types'

function makeItem(overrides: Partial<Item> = {}): Item {
  return {
    url: 'https://example.com/item',
    title: 'Tomo X',
    cluster_key: 'isbn:9780000000001',
    standardized_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

function makeCluster(overrides: Partial<Cluster> = {}): Cluster {
  const item = makeItem()
  return {
    clusterKey: item.cluster_key,
    slug: 'tomo-x',
    canonical: item,
    items: [item],
    volumeCount: 1,
    signalTypes: [],
    countries: [],
    publishers: [],
    languages: [],
    ...overrides,
  }
}

describe('compareVolumes', () => {
  it('sorts numerically', () => {
    expect(compareVolumes('2', '10')).toBeLessThan(0)
  })

  it('puts items without volume at the end (regla de orden de tomos)', () => {
    expect(compareVolumes(undefined, '1')).toBeGreaterThan(0)
    expect(compareVolumes('1', '')).toBeLessThan(0)
  })

  it('breaks the tie between a volume and a range starting at it', () => {
    // El tomo "1" va antes que el cofre "1-3" (antes empataban: parseFloat("1-3")=1)
    expect(compareVolumes('1', '1-3')).toBeLessThan(0)
    expect(compareVolumes('1-3', '1-5')).toBeLessThan(0)
    expect(compareVolumes('1-3', '2')).toBeLessThan(0)
  })
})

describe('groupByEdition', () => {
  const mk = (key: string, vol: string, isbn?: string) =>
    makeCluster({
      clusterKey: `k:${key}:${vol}`,
      slug: `slug-${key}-${vol}`,
      editionKey: key,
      volume: vol,
      canonical: makeItem({ cluster_key: `k:${key}:${vol}`, volume: vol, isbn }),
    })

  it('collapses clusters sharing edition_key and counts volumes', () => {
    const result = groupByEdition([mk('ed-a', '1'), mk('ed-a', '2'), mk('ed-b', '1')])
    expect(result).toHaveLength(2)
    expect(result[0].volumeCount).toBe(2)
    expect(result[1].volumeCount).toBe(1)
  })

  it('keeps standalone clusters (no edition_key) as-is', () => {
    const standalone = makeCluster({ editionKey: undefined })
    const result = groupByEdition([standalone])
    expect(result).toEqual([standalone])
  })

  it('promotes the most complete canonical with its slug AND volume', () => {
    const plain = mk('ed-a', '1')
    const withIsbn = mk('ed-a', '2', '9781234567890')
    const [entry] = groupByEdition([plain, withIsbn])
    expect(entry.canonical.isbn).toBe('9781234567890')
    expect(entry.slug).toBe('slug-ed-a-2')
    expect(entry.volume).toBe('2') // portada y volumen coherentes
  })

  it('preserves the input (sorted) order of first appearance', () => {
    const result = groupByEdition([mk('ed-z', '1'), mk('ed-a', '1'), mk('ed-z', '2')])
    expect(result.map(c => c.editionKey)).toEqual(['ed-z', 'ed-a'])
  })
})

describe('buildFacets', () => {
  it('counts and ranks facet values', () => {
    const clusters = [
      makeCluster({ countries: ['España'], languages: ['es'] }),
      makeCluster({ countries: ['España', 'Francia'], languages: ['es'] }),
    ]
    const facets = buildFacets(clusters)
    expect(facets.countries[0]).toEqual({ value: 'España', count: 2 })
    expect(facets.countries[1]).toEqual({ value: 'Francia', count: 1 })
    expect(facets.languages[0].count).toBe(2)
  })
})

describe('dedupeImages / imageKey', () => {
  it('normalizes scheme, query and case', () => {
    expect(imageKey('https://Host.com/a.jpg?w=200')).toBe(imageKey('http://host.com/a.jpg'))
  })

  it('dedupes by normalized URL and borrows `local` from duplicates', () => {
    const result = dedupeImages([
      { url: 'https://x.com/a.jpg', kind: 'cover' },
      { url: 'http://x.com/a.jpg?big=1', local: 'a.jpg', kind: 'gallery' },
      { url: 'https://x.com/b.jpg', kind: 'gallery' },
    ])
    expect(result).toHaveLength(2)
    expect(result[0].kind).toBe('cover')  // conserva la primera entrada…
    expect(result[0].local).toBe('a.jpg') // …pero hereda el espejo local
  })

  it('drops entries without url', () => {
    expect(dedupeImages([{ url: '', kind: 'cover' }])).toEqual([])
  })
})
