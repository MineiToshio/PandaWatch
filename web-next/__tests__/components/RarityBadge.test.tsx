import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { RarityBadge, RARITY_META, RARITY_VALUES } from '@/components/modules/RarityBadge'

// Labels de rareza en español (auditoría #10 — cierre del hallazgo: el
// reporte citaba RarityBadge.tsx:14-48 con "Accessible", "Rare"… en inglés
// dentro de un sitio lang="es"). RARITY_META sigue siendo la fuente única
// (lección del comentario del componente); no se movió a lib/vocab.ts porque
// la rareza es otro eje (no señal/tipo de edición) y sus íconos ReactNode
// exigen .tsx.

const EXPECTED_ES: Record<(typeof RARITY_VALUES)[number], string> = {
  common: 'Accesible',
  rare: 'Rara',
  super_rare: 'Súper rara',
  ultra_rare: 'Ultra rara',
}

describe('RARITY_META — labels en español', () => {
  it.each(RARITY_VALUES)('%s tiene su label en español', (value) => {
    expect(RARITY_META[value].label).toBe(EXPECTED_ES[value])
  })

  it('ningún label quedó en inglés', () => {
    const labels = RARITY_VALUES.map(v => RARITY_META[v].label)
    for (const en of ['Accessible', 'Rare', 'Super Rare', 'Ultra Rare']) {
      expect(labels).not.toContain(en)
    }
  })
})

describe('RarityBadge — render', () => {
  it.each(RARITY_VALUES)('renderiza el badge de %s con su label', (value) => {
    render(<RarityBadge rarity={value} />)
    expect(screen.getByText(EXPECTED_ES[value])).toBeInTheDocument()
  })

  it('rareza desconocida renderiza null (sin crash)', () => {
    const { container } = render(<RarityBadge rarity="mythic" />)
    expect(container).toBeEmptyDOMElement()
  })
})
