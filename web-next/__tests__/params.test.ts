import { describe, it, expect } from 'vitest'
import { parseFilterParams, paginate } from '@/lib/filters'

// Saneo de searchParams hostiles: antes ?q=a&q=b crasheaba la home con 500
// (array asumido string) y ?page=abc dejaba el catálogo vacío en "pág. NaN".

describe('parseFilterParams', () => {
  it('takes the first value when a scalar param is repeated', () => {
    const fp = parseFilterParams({ q: ['naruto', 'bleach'] })
    expect(fp.q).toBe('naruto')
  })

  it('defaults page to 1 on non-numeric / out-of-domain values', () => {
    expect(parseFilterParams({ page: 'abc' }).page).toBe(1)
    expect(parseFilterParams({ page: '-3' }).page).toBe(1)
    expect(parseFilterParams({ page: '2.5' }).page).toBe(1)
    expect(parseFilterParams({ page: '4' }).page).toBe(4)
  })

  it('falls back to date_desc on unknown sort values', () => {
    expect(parseFilterParams({ sort: 'score_desc' }).sort).toBe('date_desc')
    expect(parseFilterParams({ sort: ['title_asc', 'date_asc'] }).sort).toBe('title_asc')
  })

  it('wraps single values into arrays for array filters', () => {
    const fp = parseFilterParams({ country: 'España', rarity: ['rare', 'ultra_rare'] })
    expect(fp.country).toEqual(['España'])
    expect(fp.rarity).toEqual(['rare', 'ultra_rare'])
  })
})

describe('paginate (edge cases)', () => {
  const items = Array.from({ length: 130 }, (_, i) => i)

  it('clamps NaN to page 1 instead of returning an empty slice', () => {
    const r = paginate(items, NaN, 60)
    expect(r.page).toBe(1)
    expect(r.items.length).toBe(60)
  })

  it('clamps past-the-end pages to the last page', () => {
    const r = paginate(items, 99, 60)
    expect(r.page).toBe(3)
    expect(r.items.length).toBe(10)
  })

  it('handles an empty list without dividing by zero', () => {
    const r = paginate([], 1, 60)
    expect(r.page).toBe(1)
    expect(r.pages).toBe(0)
    expect(r.items).toEqual([])
  })
})
