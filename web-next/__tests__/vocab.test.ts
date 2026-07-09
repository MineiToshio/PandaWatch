import { describe, it, expect } from 'vitest'
import {
  VOCAB,
  LIMITED_SIGNAL_TYPES,
  signalChipMeta,
  signalProseLabel,
  editionTypeLabelFromSlug,
  editionSlugRank,
  signalRank,
  equivSignalsForSlug,
} from '@/lib/vocab'
import { editionTypeLabel } from '@/lib/format'

// Vocabulario único (auditoría #12) — antes repartido en 6 archivos con
// divergencias silenciosas (ultimate/integrale en KIND_RANK pero integral en
// EDITION_TYPE_LABELS). Estos tests fijan el contrato: todo signal_type con
// chip visual tiene entrada completa, y los 6 consumidores migrados
// (data.ts, format.ts, EditionCard, SignalChip, descriptions.ts, filters.ts)
// leen de la MISMA fuente.

// signal_types que SignalChip debe poder renderizar como chip (el set
// original de SIGNAL_META, antes de la consolidación).
const CHIP_SIGNALS = [
  'limited', 'special_edition', 'collector', 'box_set', 'variant_cover',
  'artbook', 'deluxe', 'hardcover', 'kanzenban', 'lore_edition', 'omnibus',
  'bonus', 'retailer_exclusive',
]

describe('VOCAB — cobertura de señales con chip visual', () => {
  it.each(CHIP_SIGNALS)('%s tiene labelEs + icon + bg + fg', (signal) => {
    const meta = signalChipMeta(signal)
    expect(meta).not.toBeNull()
    expect(meta!.label.length).toBeGreaterThan(0)
    expect(meta!.icon).toBeDefined()
    expect(meta!.bg).toMatch(/^#/)
    expect(meta!.fg).toMatch(/^#/)
  })

  it('signal desconocida no tiene chip (SignalChip debe renderizar null)', () => {
    expect(signalChipMeta('not_a_real_signal')).toBeNull()
  })
})

describe('LIMITED_SIGNAL_TYPES — filtro "sólo ediciones limitadas"', () => {
  it('coincide exactamente con el set original de 10 señales', () => {
    const expected = new Set([
      'limited', 'special_edition', 'collector', 'lore_edition',
      'variant_cover', 'artbook', 'kanzenban', 'deluxe', 'box_set',
      'retailer_exclusive',
    ])
    expect(LIMITED_SIGNAL_TYPES).toEqual(expected)
  })

  it('hardcover/omnibus/bonus NO cuentan como limitadas (comportamiento preservado)', () => {
    expect(LIMITED_SIGNAL_TYPES.has('hardcover')).toBe(false)
    expect(LIMITED_SIGNAL_TYPES.has('omnibus')).toBe(false)
    expect(LIMITED_SIGNAL_TYPES.has('bonus')).toBe(false)
  })
})

describe('signalProseLabel — prosa de descriptions.ts', () => {
  it('devuelve el label en minúscula para señales conocidas', () => {
    expect(signalProseLabel('limited')).toBe('edición limitada')
    expect(signalProseLabel('box_set')).toBe('box set')
  })

  it('fallback determinístico (guiones bajos → espacios) para señales sin vocab', () => {
    expect(signalProseLabel('some_unknown_signal')).toBe('some unknown signal')
  })
})

describe('editionTypeLabel — badge de tipo de edición (vía format.ts)', () => {
  it('resuelve el slug del edition_key a un label conocido', () => {
    expect(editionTypeLabel('one-piece-glenat-boxset-fr')).toBe('Box Set')
    expect(editionTypeLabel('berserk-darkhorse-deluxe-us')).toBe('Deluxe')
  })

  it('"regular" nunca badgea (caso especial preservado)', () => {
    expect(editionTypeLabel('serie-editorial-regular-es')).toBeNull()
  })

  it('fix de la divergencia ES/FR: integral e integrale comparten label', () => {
    expect(editionTypeLabelFromSlug('integral')).toBe('Integral')
    expect(editionTypeLabelFromSlug('integrale')).toBe('Integral')
  })

  it('slugs que sólo aportan rank (no badge) no rompen el consumidor — comportamiento preservado', () => {
    // "especial"/"limitada"/"box" nunca tuvieron label en EDITION_TYPE_LABELS
    expect(editionTypeLabelFromSlug('especial')).toBeNull()
    expect(editionTypeLabelFromSlug('limitada')).toBeNull()
    expect(editionTypeLabelFromSlug('box')).toBeNull()
  })
})

describe('equivSignalsForSlug — EditionCard omite chips redundantes con el badge', () => {
  it('boxset/coffret/cofanetto son equivalentes a box_set', () => {
    expect(equivSignalsForSlug('boxset')).toEqual(['box_set'])
    expect(equivSignalsForSlug('coffret')).toEqual(['box_set'])
  })

  it('slug sin equivalencias devuelve array vacío', () => {
    expect(equivSignalsForSlug('perfect')).toEqual([])
  })
})

describe('rank — desempate de tomos (gotcha #60, kindRank en data.ts)', () => {
  it('edición-slug: regular < variant < special < deluxe < artbook < box', () => {
    expect(editionSlugRank('regular')).toBe(0)
    expect(editionSlugRank('variant')).toBe(1)
    expect(editionSlugRank('special')).toBe(2)
    expect(editionSlugRank('deluxe')).toBe(3)
    expect(editionSlugRank('artbook')).toBe(4)
    expect(editionSlugRank('boxset')).toBe(5)
  })

  it('señal: toma el mínimo entre las señales del cluster', () => {
    expect(signalRank(['box_set', 'variant_cover'])).toBe(1) // variant_cover gana
    expect(signalRank(['special_edition'])).toBe(2)
  })

  it('señal sin rank conocido → undefined (kindRank cae al default 10)', () => {
    expect(signalRank(['lore_edition', 'bonus'])).toBeUndefined()
  })
})

describe('VOCAB — sin claves vacías', () => {
  it('toda entrada tiene al menos un campo útil (labelEs o rank)', () => {
    for (const [key, entry] of Object.entries(VOCAB)) {
      expect(entry.labelEs !== undefined || entry.rank !== undefined, `vocab["${key}"] está vacío`).toBe(true)
    }
  })
})
