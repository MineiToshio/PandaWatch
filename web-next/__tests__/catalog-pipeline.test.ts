import { describe, it, expect } from 'vitest'
import { groupByEdition } from '@/lib/data'
import { filterClusters, sortClusters, paginate, parseFilterParams } from '@/lib/filters'
import type { Cluster, Item } from '@/lib/types'

/**
 * Integración del pipeline de la home: filter → sort → group → paginate
 * (auditoría #20 — encadenado tal cual app/page.tsx, antes sin cobertura de
 * integración; cada función tenía tests unitarios propios pero nada probaba
 * que la composición se comportara igual que en producción). ~20 clusters
 * fixture repartidos en 5 ediciones multi-volumen + clusters standalone,
 * varios países/idiomas/señales para ejercitar filtro + orden + agrupación
 * + paginación juntos.
 */

function makeItem(overrides: Partial<Item> = {}): Item {
  return {
    url: 'https://example.com/item',
    title: 'Tomo',
    cluster_key: 'k:default',
    standardized_at: '2026-01-01T00:00:00Z',
    country: 'España',
    language: 'es',
    publisher: 'Editorial X',
    signal_types: [],
    ...overrides,
  }
}

function makeCluster(overrides: Partial<Cluster> = {}): Cluster {
  const item = overrides.canonical ?? makeItem()
  return {
    clusterKey: item.cluster_key,
    slug: `slug-${item.cluster_key}`,
    canonical: item,
    items: [item],
    volumeCount: 1,
    signalTypes: item.signal_types ?? [],
    countries: item.country ? [item.country] : [],
    publishers: item.publisher ? [item.publisher] : [],
    languages: item.language ? [item.language] : [],
    ...overrides,
  }
}

// 3 ediciones de 3 tomos (9 clusters) + 1 edición de 2 tomos (2) + 9 clusters
// standalone = 20 clusters, mezclando países/señales/fechas.
function buildFixture(): Cluster[] {
  const clusters: Cluster[] = []

  const editions = [
    { key: 'berserk-darkhorse-deluxe-us', series: 'Berserk', country: 'Estados Unidos', signals: ['deluxe'] },
    { key: 'one-piece-glenat-boxset-fr', series: 'One Piece', country: 'Francia', signals: ['box_set'] },
    { key: 'demon-slayer-panini-limited-es', series: 'Demon Slayer', country: 'España', signals: ['limited'] },
  ]
  for (const ed of editions) {
    for (let vol = 1; vol <= 3; vol++) {
      const item = makeItem({
        cluster_key: `k:${ed.key}:${vol}`,
        title: `${ed.series} ${vol}`,
        series_display: ed.series,
        series_key: ed.series.toLowerCase().replace(/\s+/g, '-'),
        edition_key: ed.key,
        edition_display: `${ed.series} Edition`,
        country: ed.country,
        signal_types: ed.signals,
        release_date: `2024-0${vol}-01`,
      })
      clusters.push(makeCluster({
        clusterKey: item.cluster_key,
        slug: `${ed.key}-${vol}`,
        canonical: item,
        items: [item],
        editionKey: ed.key,
        editionDisplay: `${ed.series} Edition`,
        seriesDisplay: ed.series,
        volume: String(vol),
        signalTypes: ed.signals,
        countries: [ed.country],
        publishers: ['Editorial X'],
        languages: ['es'],
      }))
    }
  }

  // Edición de 2 tomos, Italia, kanzenban
  for (let vol = 1; vol <= 2; vol++) {
    const item = makeItem({
      cluster_key: `k:jojo-star-kanzenban-it:${vol}`,
      title: `JoJo ${vol}`,
      series_display: 'JoJo',
      series_key: 'jojo',
      edition_key: 'jojo-star-kanzenban-it',
      country: 'Italia',
      signal_types: ['kanzenban'],
      release_date: `2023-0${vol}-01`,
    })
    clusters.push(makeCluster({
      clusterKey: item.cluster_key,
      slug: `jojo-kanzenban-${vol}`,
      canonical: item,
      items: [item],
      editionKey: 'jojo-star-kanzenban-it',
      editionDisplay: 'JoJo Kanzenban',
      seriesDisplay: 'JoJo',
      volume: String(vol),
      signalTypes: ['kanzenban'],
      countries: ['Italia'],
      publishers: ['Editorial X'],
      languages: ['it'],
    }))
  }

  // 9 clusters standalone (sin edición), distintas series/fechas
  for (let i = 1; i <= 9; i++) {
    const item = makeItem({
      cluster_key: `k:standalone-${i}`,
      title: `Obra Suelta ${i}`,
      series_display: `Obra Suelta ${i}`,
      release_date: `2022-0${(i % 9) + 1}-01`,
    })
    clusters.push(makeCluster({
      clusterKey: item.cluster_key,
      slug: `standalone-${i}`,
      canonical: item,
      items: [item],
    }))
  }

  return clusters
}

const FIXTURE = buildFixture()

describe('pipeline del catálogo — filter → sort → group → paginate', () => {
  it('sin filtros: 20 clusters se agrupan en 4 ediciones + 9 standalone = 13 tarjetas', () => {
    const fp = parseFilterParams({})
    const filtered = filterClusters(FIXTURE, fp)
    expect(filtered).toHaveLength(20)
    const sorted = sortClusters(filtered, fp.sort)
    const editions = groupByEdition(sorted)
    // 3 ediciones de 3 tomos + 1 de 2 tomos = 4 tarjetas de edición + 9 standalone
    expect(editions).toHaveLength(13)
    const berserkCard = editions.find(c => c.editionKey === 'berserk-darkhorse-deluxe-us')
    expect(berserkCard?.volumeCount).toBe(3)
  })

  it('filtro por país reduce ANTES de agrupar (una edición completa desaparece si no matchea)', () => {
    const fp = parseFilterParams({ country: ['Francia'] })
    const filtered = filterClusters(FIXTURE, fp)
    expect(filtered).toHaveLength(3) // los 3 tomos de One Piece
    const editions = groupByEdition(sortClusters(filtered, fp.sort))
    expect(editions).toHaveLength(1)
    expect(editions[0].editionKey).toBe('one-piece-glenat-boxset-fr')
    expect(editions[0].volumeCount).toBe(3)
  })

  it('only_limited excluye ediciones sin señal limitada (kanzenban SÍ cuenta, deluxe SÍ cuenta)', () => {
    const fp = parseFilterParams({ only_limited: 'true' })
    const filtered = filterClusters(FIXTURE, fp)
    // deluxe(3) + box_set(3) + limited(3) + kanzenban(2) = 11; los 9 standalone sin señales quedan afuera
    expect(filtered).toHaveLength(11)
  })

  it('sort date_desc ordena por fecha ANTES de agrupar (agrupar preserva la posición del primer tomo)', () => {
    const fp = parseFilterParams({ sort: 'date_desc' })
    const filtered = filterClusters(FIXTURE, fp)
    const sorted = sortClusters(filtered, fp.sort)
    const editions = groupByEdition(sorted)
    // Berserk (2024-03 el tomo más reciente de esa edición) debe aparecer
    // antes que JoJo (2023) en el resultado agrupado.
    const berserkIdx = editions.findIndex(c => c.editionKey === 'berserk-darkhorse-deluxe-us')
    const jojoIdx = editions.findIndex(c => c.editionKey === 'jojo-star-kanzenban-it')
    expect(berserkIdx).toBeGreaterThanOrEqual(0)
    expect(jojoIdx).toBeGreaterThan(berserkIdx)
  })

  it('paginate corta el resultado YA agrupado (13 tarjetas caben en 1 página de 60)', () => {
    const fp = parseFilterParams({})
    const filtered = filterClusters(FIXTURE, fp)
    const editions = groupByEdition(sortClusters(filtered, fp.sort))
    const { items, pages, total } = paginate(editions, fp.page, 60)
    expect(total).toBe(13)
    expect(pages).toBe(1)
    expect(items).toHaveLength(13)
  })

  it('paginate con pageSize chico corta correctamente el resultado agrupado', () => {
    const fp = parseFilterParams({})
    const filtered = filterClusters(FIXTURE, fp)
    const editions = groupByEdition(sortClusters(filtered, fp.sort))
    const page1 = paginate(editions, 1, 5)
    const page2 = paginate(editions, 2, 5)
    expect(page1.items).toHaveLength(5)
    expect(page2.items).toHaveLength(5)
    expect(page1.pages).toBe(3) // 13 / 5 = 3 páginas
    // Ninguna tarjeta se repite entre páginas
    const overlap = page1.items.filter(a => page2.items.some(b => b.clusterKey === a.clusterKey))
    expect(overlap).toHaveLength(0)
  })

  it('búsqueda + agrupación: "berserk" deja sólo esa edición completa', () => {
    const fp = parseFilterParams({ q: 'berserk' })
    const filtered = filterClusters(FIXTURE, fp)
    expect(filtered).toHaveLength(3)
    const editions = groupByEdition(sortClusters(filtered, fp.sort))
    expect(editions).toHaveLength(1)
    expect(editions[0].volumeCount).toBe(3)
  })
})
