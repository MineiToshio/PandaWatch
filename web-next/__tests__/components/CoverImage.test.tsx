import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { CoverImage } from '@/components/modules/CoverImage'

// Cadena de fallback (auditoría #20): espejo local → URL remota → placeholder.
// Un fallo silencioso acá deja portadas rotas en TODO el catálogo (60 cards
// por página), así que la cadena completa merece cobertura directa.

describe('CoverImage — cadena de fallback', () => {
  it('con imageLocal, usa el espejo local (/images/...) — next/image lo pasa por el optimizer', () => {
    render(<CoverImage imageLocal="cover.avif" imageUrl="https://store.example/cover.jpg" alt="Portada" fill />)
    const img = screen.getByRole('img', { name: 'Portada' })
    expect(img.getAttribute('src')).toContain(encodeURIComponent('/images/cover.avif'))
  })

  it('local → onError → cae a la URL remota', () => {
    render(<CoverImage imageLocal="cover.avif" imageUrl="https://store.example/cover.jpg" alt="Portada" fill />)
    const img = screen.getByRole('img', { name: 'Portada' })
    fireEvent.error(img)
    const fallback = screen.getByRole('img', { name: 'Portada' })
    expect(fallback).toHaveAttribute('src', 'https://store.example/cover.jpg')
    // El <img> remoto manda no-referrer (auditoría #15 — muchas tiendas
    // bloquean hotlinks por Referer).
    expect(fallback).toHaveAttribute('referrerpolicy', 'no-referrer')
  })

  it('local → error → remota → error → placeholder (BookOpen, sin <img>)', () => {
    render(<CoverImage imageLocal="cover.avif" imageUrl="https://store.example/cover.jpg" alt="Portada" fill />)
    const img = screen.getByRole('img', { name: 'Portada' })
    fireEvent.error(img)
    const remote = screen.getByRole('img', { name: 'Portada' })
    fireEvent.error(remote)
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })

  it('sin imageLocal, usa directamente la URL remota', () => {
    render(<CoverImage imageUrl="https://store.example/cover.jpg" alt="Portada" fill />)
    const img = screen.getByRole('img', { name: 'Portada' })
    expect(img).toHaveAttribute('src', 'https://store.example/cover.jpg')
  })

  it('sin imageLocal ni imageUrl, placeholder directo (sin <img>)', () => {
    render(<CoverImage alt="Portada" />)
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })
})
