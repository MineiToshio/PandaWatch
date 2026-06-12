import { describe, it, expect } from 'vitest'
import { formatDate, sortableDate } from '@/lib/format'

// Los 4 formatos reales del corpus: ISO, YYYY-MM, YYYY y DD/MM/YYYY.
// El bug original: "2026" parseado como UTC se mostraba "31 dic 2025" en
// timezones negativas, y "06/05/2025" se interpretaba MM/DD.

describe('formatDate', () => {
  it('formats full ISO dates in local time (no day shift)', () => {
    expect(formatDate('2026-03-15')).toMatch(/15.*mar.*2026/)
  })

  it('shows only the year for YYYY (no backwards shift)', () => {
    expect(formatDate('2026')).toBe('2026')
  })

  it('shows month + year for YYYY-MM (no month shift)', () => {
    expect(formatDate('2026-03')).toMatch(/mar.*2026/)
    expect(formatDate('2026-03')).not.toMatch(/feb/)
  })

  it('parses DD/MM/YYYY as day-first', () => {
    // 06/05/2025 = 6 de mayo, no 5 de junio
    expect(formatDate('06/05/2025')).toMatch(/6.*may.*2025/)
    // 28/10/2025 sería inválido como MM/DD — debe parsear día-primero
    expect(formatDate('28/10/2025')).toMatch(/28.*oct.*2025/)
  })

  it('returns invalid input untouched', () => {
    expect(formatDate('???')).toBe('???')
    expect(formatDate('99/99/9999')).toBe('99/99/9999')
  })
})

describe('sortableDate', () => {
  it('reorders DD/MM/YYYY so date sorting is correct', () => {
    const dates = ['2024-03-15', '31/10/2023', '2026']
    const sorted = [...dates].sort((a, b) => sortableDate(b).localeCompare(sortableDate(a)))
    // El más reciente debe ser "2026", no el item DD/MM/YYYY de 2023
    expect(sorted[0]).toBe('2026')
    expect(sorted[2]).toBe('31/10/2023')
  })

  it('keeps ISO and partial dates as-is', () => {
    expect(sortableDate('2026-03-15')).toBe('2026-03-15')
    expect(sortableDate('2026-03')).toBe('2026-03')
    expect(sortableDate('2026')).toBe('2026')
  })
})
