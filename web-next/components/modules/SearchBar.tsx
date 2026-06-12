'use client'

import { useState, useRef, useEffect } from 'react'
import { useRouter, useSearchParams, usePathname } from 'next/navigation'

export function SearchBar() {
  const router     = useRouter()
  const pathname   = usePathname()
  const params     = useSearchParams()

  const [focused, setFocused] = useState(false)
  const [query, setQuery]     = useState(params.get('q') ?? '')
  const debounceRef  = useRef<ReturnType<typeof setTimeout> | null>(null)
  const focusedRef   = useRef(false)   // ref copy so useEffect can read it synchronously
  const inputRef     = useRef<HTMLInputElement>(null)

  // Sync URL → input only when the user is NOT actively typing.
  // Without this guard, router.replace() triggers params to change which
  // calls setQuery() mid-keystroke, clobbering whatever the user typed.
  useEffect(() => {
    if (!focusedRef.current) {
      setQuery(params.get('q') ?? '')
    }
  }, [params])

  // Cancelar el debounce pendiente al desmontar (navegación mid-typing)
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [])

  function commit(value: string) {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = null
    // El buscador vive en el Header de TODAS las páginas, pero la búsqueda es
    // del catálogo: desde una ficha/edición/serie navega a `/?q=…` (la página
    // de detalle es estática e ignora searchParams).
    if (pathname !== '/') {
      if (value.trim()) router.push(`/?q=${encodeURIComponent(value.trim())}`)
      return
    }
    // URL viva (no el snapshot del hook): si un filtro cambió durante la
    // ventana del debounce, no hay que pisarlo con params stale.
    const next = new URLSearchParams(window.location.search)
    if (value.trim()) {
      next.set('q', value.trim())
    } else {
      next.delete('q')
    }
    next.delete('page')
    router.replace(`${pathname}?${next.toString()}`)
  }

  function handleChange(value: string) {
    setQuery(value)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => commit(value), 600)
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') {
      e.preventDefault()
      commit(query)
    }
  }

  function handleFocus() {
    focusedRef.current = true
    setFocused(true)
  }

  function handleBlur() {
    focusedRef.current = false
    setFocused(false)
  }

  function handleClear() {
    setQuery('')
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = null
    if (pathname !== '/') return // en detalle no hay búsqueda aplicada que limpiar
    const next = new URLSearchParams(window.location.search)
    next.delete('q')
    next.delete('page')
    router.replace(`${pathname}?${next.toString()}`)
  }

  return (
    <div
      style={{
        flex: 1,
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        background: focused ? '#fff' : '#F5F1EB',
        border: focused ? '1.5px solid #1A8A5A' : '1.5px solid #DDD8CF',
        boxShadow: focused ? '0 0 0 3px rgba(26,138,90,0.12)' : 'none',
        borderRadius: 8,
        padding: '0 14px',
        height: 38,
        transition: 'border-color 150ms, box-shadow 150ms, background 150ms',
        cursor: 'text',
      }}
      onClick={() => inputRef.current?.focus()}
    >
      <svg
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke={focused ? '#1A8A5A' : '#A89E93'}
        strokeWidth="2"
        aria-hidden="true"
        style={{ flexShrink: 0 }}
      >
        <circle cx="11" cy="11" r="8" />
        <line x1="21" y1="21" x2="16.65" y2="16.65" />
      </svg>

      <input
        ref={inputRef}
        // type="text" (no "search"): WebKit/Chrome pintan su ✕ nativo junto al
        // botón clear custom y quedan dos
        type="text"
        role="searchbox"
        enterKeyHint="search"
        placeholder="Buscar por manga, serie, editorial, ISBN…"
        value={query}
        onChange={(e) => handleChange(e.target.value)}
        onKeyDown={handleKeyDown}
        onFocus={handleFocus}
        onBlur={handleBlur}
        style={{
          flex: 1,
          border: 'none',
          background: 'transparent',
          outline: 'none',
          fontFamily: "var(--font-body)",
          fontSize: 14,
          color: '#1C1915',
        }}
      />

      {query && (
        <button
          type="button"
          onClick={handleClear}
          aria-label="Clear search"
          style={{
            display: 'flex',
            cursor: 'pointer',
            color: '#A89E93',
            background: 'none',
            border: 'none',
            padding: 0,
          }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <circle cx="12" cy="12" r="10" />
            <line x1="15" y1="9" x2="9" y2="15" />
            <line x1="9" y1="9" x2="15" y2="15" />
          </svg>
        </button>
      )}
    </div>
  )
}

export default SearchBar
