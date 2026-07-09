import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { EditionCard } from '@/components/catalog/EditionCard'
import type { Cluster, Item } from '@/lib/types'

// Cobertura de componentes (auditoría #20 — antes 0 tests). EditionCard es el
// link principal del catálogo: multi-volumen va a /edition/[editionKey],
// single-volumen/standalone va a /item/[slug]. Un bug acá manda al usuario a
// la página equivocada silenciosamente (el href no lanza error).

function makeItem(overrides: Partial<Item> = {}): Item {
  return {
    url: 'https://example.com/item',
    title: 'Berserk Deluxe 1',
    cluster_key: 'isbn:9781506711980',
    standardized_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

function makeCluster(overrides: Partial<Cluster> = {}): Cluster {
  const item = makeItem()
  return {
    clusterKey: item.cluster_key,
    slug: 'berserk-darkhorse-deluxe-1',
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

describe('EditionCard — href', () => {
  it('multi-volumen (volumeCount > 1 con editionKey) → /edition/[editionKey]', () => {
    const cluster = makeCluster({
      editionKey: 'berserk-darkhorse-deluxe-us',
      volumeCount: 3,
    })
    render(<EditionCard cluster={cluster} />)
    const link = screen.getByRole('link')
    expect(link).toHaveAttribute('href', '/edition/berserk-darkhorse-deluxe-us')
  })

  it('single-volumen con slug → /item/[slug] (no /edition/, aunque tenga editionKey)', () => {
    const cluster = makeCluster({
      editionKey: 'berserk-darkhorse-deluxe-us',
      volumeCount: 1,
      slug: 'berserk-darkhorse-deluxe-1',
    })
    render(<EditionCard cluster={cluster} />)
    const link = screen.getByRole('link')
    expect(link).toHaveAttribute('href', '/item/berserk-darkhorse-deluxe-1')
  })

  it('standalone (sin editionKey) con slug → /item/[slug]', () => {
    const cluster = makeCluster({ editionKey: undefined, volumeCount: 1, slug: 'obscure-artbook' })
    render(<EditionCard cluster={cluster} />)
    const link = screen.getByRole('link')
    expect(link).toHaveAttribute('href', '/item/obscure-artbook')
  })

  it('sin slug ni edición usable → "#" (no crashea, no linkea a nada)', () => {
    const cluster = makeCluster({ editionKey: undefined, volumeCount: 1, slug: '' })
    render(<EditionCard cluster={cluster} />)
    const link = screen.getByRole('link')
    expect(link).toHaveAttribute('href', '#')
  })

  it('multi-volumen SIN editionKey (dato inconsistente) cae a /item/[slug]', () => {
    const cluster = makeCluster({ editionKey: undefined, volumeCount: 3, slug: 'weird-case' })
    render(<EditionCard cluster={cluster} />)
    const link = screen.getByRole('link')
    expect(link).toHaveAttribute('href', '/item/weird-case')
  })
})

describe('EditionCard — título y chips', () => {
  it('muestra el título oficial sin transformarlo', () => {
    const cluster = makeCluster({
      canonical: makeItem({ title: 'Berserk Deluxe 1' }),
    })
    render(<EditionCard cluster={cluster} />)
    expect(screen.getByText('Berserk Deluxe 1')).toBeInTheDocument()
  })

  it('EditionTypeChip + SignalChip conviven sin repetir el mismo concepto (equivSignals)', () => {
    const cluster = makeCluster({
      editionKey: 'one-piece-glenat-boxset-fr',
      volumeCount: 2,
      signalTypes: ['box_set', 'limited'],
    })
    render(<EditionCard cluster={cluster} />)
    // "Box Set" del EditionTypeChip aparece una sola vez (no también como SignalChip)
    expect(screen.getAllByText('Box Set')).toHaveLength(1)
  })
})
