import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { itemJsonLd } from '@/lib/jsonld'
import type { Cluster, Item } from '@/lib/types'

// Origin/imágenes deterministas (fallback localhost, sin bucket).
const ENV_KEYS = ['NEXT_PUBLIC_SITE_URL', 'VERCEL_URL', 'VERCEL_PROJECT_PRODUCTION_URL', 'NEXT_PUBLIC_IMAGE_BASE_URL'] as const
let saved: Record<string, string | undefined>
beforeEach(() => {
  saved = {}
  for (const k of ENV_KEYS) { saved[k] = process.env[k]; delete process.env[k] }
})
afterEach(() => {
  for (const k of ENV_KEYS) {
    if (saved[k] === undefined) delete process.env[k]; else process.env[k] = saved[k]
  }
})

function makeItem(overrides: Partial<Item> = {}): Item {
  return {
    url: 'https://example.com/item',
    title: 'Berserk Deluxe 1',
    cluster_key: 'lmc:1:deluxe:1',
    standardized_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}
function makeCluster(overrides: Partial<Cluster> = {}): Cluster {
  const item = makeItem()
  return {
    clusterKey: item.cluster_key,
    slug: 'berserk-deluxe-1',
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

describe('itemJsonLd — tipo (auditoría #5)', () => {
  it('con ISBN → @type Book con isbn/author/publisher/datePublished/inLanguage', () => {
    const cluster = makeCluster({
      canonical: makeItem({
        isbn: '9781506711980',
        author: 'Kentaro Miura',
        publisher: 'Dark Horse',
        release_date: '2019-05-14',
        language: 'en',
      }),
    })
    const ld = itemJsonLd(cluster, 'berserk-deluxe-1')
    expect(ld['@type']).toBe('Book')
    expect(ld.isbn).toBe('9781506711980')
    expect(ld.author).toEqual({ '@type': 'Person', name: 'Kentaro Miura' })
    expect(ld.publisher).toEqual({ '@type': 'Organization', name: 'Dark Horse' })
    expect(ld.datePublished).toBe('2019-05-14')
    expect(ld.inLanguage).toBe('en')
  })

  it('sin ISBN → @type CreativeWork (sin isbn)', () => {
    const ld = itemJsonLd(makeCluster(), 'berserk-deluxe-1')
    expect(ld['@type']).toBe('CreativeWork')
    expect('isbn' in ld).toBe(false)
  })

  it('NUNCA emite Product (Google exige offers y no hay precios)', () => {
    const withIsbn = itemJsonLd(makeCluster({ canonical: makeItem({ isbn: '9781506711980' }) }), 's')
    const without = itemJsonLd(makeCluster(), 's')
    expect(JSON.stringify(withIsbn)).not.toContain('Product')
    expect(JSON.stringify(without)).not.toContain('Product')
    // Sin offers/price/priceCurrency en ningún caso (decisión sin precios)
    expect(JSON.stringify(withIsbn)).not.toMatch(/offers|price/i)
  })
})

describe('itemJsonLd — imagen local-first (auditoría #5)', () => {
  it('prefiere el espejo local sobre la URL remota', () => {
    const cluster = makeCluster({
      canonical: makeItem({
        images: [{ url: 'https://store.com/remote.jpg', local: 'cover.avif', kind: 'cover' }],
      }),
    })
    const ld = itemJsonLd(cluster, 's')
    expect(ld.image).toBe('http://localhost:3000/images/cover.avif')
  })

  it('cae a la URL remota si no hay espejo local', () => {
    const cluster = makeCluster({
      canonical: makeItem({
        images: [{ url: 'https://store.com/remote.jpg', kind: 'cover' }],
      }),
    })
    const ld = itemJsonLd(cluster, 's')
    expect(ld.image).toBe('https://store.com/remote.jpg')
  })

  it('omite image cuando no hay ninguna', () => {
    const ld = itemJsonLd(makeCluster(), 's')
    expect('image' in ld).toBe(false)
  })

  it('el espejo local respeta NEXT_PUBLIC_IMAGE_BASE_URL', () => {
    process.env.NEXT_PUBLIC_IMAGE_BASE_URL = 'https://cdn.example.com'
    const cluster = makeCluster({
      canonical: makeItem({ images: [{ url: 'https://s.com/r.jpg', local: 'cover.avif', kind: 'cover' }] }),
    })
    expect(itemJsonLd(cluster, 's').image).toBe('https://cdn.example.com/cover.avif')
  })
})
