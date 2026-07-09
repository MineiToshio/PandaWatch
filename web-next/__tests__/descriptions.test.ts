import { describe, it, expect } from 'vitest'
import { itemDescription, editionDescription, seriesDescription } from '@/lib/descriptions'
import type { Cluster, Item, Series } from '@/lib/types'

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

describe('itemDescription', () => {
  it('prefiere la prosa almacenada (description_es) sobre el template', () => {
    const cluster = makeCluster({
      canonical: makeItem({ description_es: 'Edición deluxe con sobrecubierta.' }),
    })
    expect(itemDescription(cluster)).toBe('Edición deluxe con sobrecubierta.')
  })

  it('cae a description (no _es) si no hay español almacenado', () => {
    const cluster = makeCluster({ canonical: makeItem({ description: 'Deluxe hardcover edition.' }) })
    expect(itemDescription(cluster)).toBe('Deluxe hardcover edition.')
  })

  it('limpia el boilerplate "MÁS INFORMACIÓN" del inicio', () => {
    const cluster = makeCluster({
      canonical: makeItem({ description_es: 'MÁS INFORMACIÓN: incluye láminas.' }),
    })
    expect(itemDescription(cluster)).toBe('incluye láminas.')
  })

  it('compone un template determinista cuando no hay prosa', () => {
    const cluster = makeCluster({
      seriesDisplay: 'Berserk',
      editionDisplay: 'Deluxe Edition',
      signalTypes: ['deluxe', 'hardcover'],
      canonical: makeItem({
        volume: '1',
        publisher: 'Dark Horse',
        country: 'USA',
        language: 'en',
      }),
    })
    expect(itemDescription(cluster)).toBe(
      'Berserk Deluxe Edition, Vol. 1 — edición deluxe, tapa dura en en publicada por Dark Horse · USA.'
    )
  })

  it('el template nunca queda vacío (fallback "edición física especial")', () => {
    const cluster = makeCluster({
      seriesDisplay: 'Serie X',
      signalTypes: [],
      canonical: makeItem({ title: 'Serie X', volume: undefined, publisher: undefined, country: undefined, language: undefined }),
    })
    expect(itemDescription(cluster)).toBe('Serie X — edición física especial.')
  })

  it('el template es determinista (misma entrada → misma salida)', () => {
    const cluster = makeCluster({ seriesDisplay: 'Naruto', signalTypes: ['box_set'] })
    expect(itemDescription(cluster)).toBe(itemDescription(cluster))
  })
})

describe('editionDescription', () => {
  it('pluraliza tomos y agrega editorial/país e idioma', () => {
    const cluster = makeCluster({
      editionDisplay: 'One Piece Box Set',
      canonical: makeItem({ publisher: 'Glénat', country: 'France', language: 'fr' }),
    })
    const out = editionDescription(cluster, 3, ['box_set'])
    expect(out).toBe('One Piece Box Set: 3 tomos de Glénat · France — box set. Edición en fr.')
  })

  it('singular "tomo" cuando totalVolumes = 1', () => {
    const cluster = makeCluster({ editionDisplay: 'Artbook X', canonical: makeItem({}) })
    const out = editionDescription(cluster, 1, ['artbook'])
    expect(out).toContain('1 tomo')
    expect(out).not.toContain('1 tomos')
  })
})

describe('seriesDescription', () => {
  const series: Series = {
    seriesKey: 'berserk',
    seriesDisplay: 'Berserk',
    cover: {},
    editionCount: 2,
    itemCount: 15,
    countries: ['Japan', 'USA'],
    publishers: ['Hakusensha', 'Dark Horse'],
    signalTypes: ['deluxe'],
  }

  it('resume ediciones/tomos con editoriales y países', () => {
    expect(seriesDescription(series)).toBe(
      'Berserk: 2 ediciones especiales (15 tomos) de Hakusensha, Dark Horse. Disponibles en Japan, USA.'
    )
  })

  it('singulariza cuando hay una sola edición y un solo tomo', () => {
    const one: Series = { ...series, editionCount: 1, itemCount: 1, publishers: [], countries: [] }
    expect(seriesDescription(one)).toBe('Berserk: 1 edición especial (1 tomo).')
  })
})
