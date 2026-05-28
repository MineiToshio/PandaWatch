'use client'

import { useState, useRef, useEffect } from 'react'
import { useRouter, useSearchParams, usePathname } from 'next/navigation'

export function SearchBar() {
  const router   = useRouter()
  const pathname = usePathname()
  const params   = useSearchParams()

  const [focused, setFocused] = useState(false)
  const [query, setQuery] = useState(params.get('q') ?? '')
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Sync if URL changes externally (back/forward)
  useEffect(() => {
    setQuery(params.get('q') ?? '')
  }, [params])

  function handleChange(value: string) {
    setQuery(value)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      const next = new URLSearchParams(params.toString())
      if (value.trim()) {
        next.set('q', value.trim())
      } else {
        next.delete('q')
      }
      next.delete('page')
      router.replace(`${pathname}?${next.toString()}`)
    }, 300)
  }

  function handleClear() {
    setQuery('')
    if (debounceRef.current) clearTimeout(debounceRef.current)
    const next = new URLSearchParams(params.toString())
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
        type="search"
        placeholder="Search by manga, series, publisher, ISBN…"
        value={query}
        onChange={(e) => handleChange(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
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
