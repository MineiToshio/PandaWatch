'use client'

import { useRouter, useSearchParams, usePathname } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'
import { X, Search } from 'lucide-react'
import type { Facets, FilterParams } from '@/lib/types'
import { SignalChip } from '@/components/modules/SignalChip'
import { CountryFlag } from '@/components/modules/CountryFlag'

type SidebarFiltersProps = {
  facets: Facets
  current: FilterParams
  isOpen: boolean
  onClose: () => void
}

const SIGNAL_DISPLAY_LIMIT = 8

export function SidebarFilters({ facets, current, isOpen, onClose }: SidebarFiltersProps) {
  const router   = useRouter()
  const pathname = usePathname()
  const params   = useSearchParams()

  // Local search text with debounce
  const [searchText, setSearchText] = useState(current.q ?? '')
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Sync if URL changes externally (e.g. back/forward)
  useEffect(() => {
    setSearchText(current.q ?? '')
  }, [current.q])

  function updateParam(key: string, value: string | null) {
    const next = new URLSearchParams(params.toString())
    if (value === null || value === '') {
      next.delete(key)
    } else {
      next.set(key, value)
    }
    next.delete('page')
    router.replace(`${pathname}?${next.toString()}`)
  }

  function toggleArrayParam(key: string, value: string) {
    const next = new URLSearchParams(params.toString())
    const existing = next.getAll(key)
    if (existing.includes(value)) {
      next.delete(key)
      existing.filter(v => v !== value).forEach(v => next.append(key, v))
    } else {
      next.append(key, value)
    }
    next.delete('page')
    router.replace(`${pathname}?${next.toString()}`)
  }

  function handleSearch(value: string) {
    setSearchText(value)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      updateParam('q', value.trim() || null)
    }, 300)
  }

  function clearAll() {
    router.replace(pathname)
    setSearchText('')
    onClose()
  }

  const hasActiveFilters =
    !!current.q ||
    (current.country?.length ?? 0) > 0 ||
    (current.language?.length ?? 0) > 0 ||
    (current.signal_types?.length ?? 0) > 0 ||
    (current.publisher?.length ?? 0) > 0 ||
    current.only_limited ||
    (current.min_score !== undefined && current.min_score > 0)

  const content = (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '14px 16px',
          borderBottom: '1px solid var(--color-border)',
          flexShrink: 0,
        }}
      >
        <span
          style={{
            fontSize: 13,
            fontWeight: 600,
            fontFamily: 'var(--font-display)',
            color: 'var(--color-text-primary)',
          }}
        >
          Filtros
        </span>
        <div style={{ display: 'flex', gap: 8 }}>
          {hasActiveFilters && (
            <button
              onClick={clearAll}
              style={{
                fontSize: 12,
                color: 'var(--color-secondary)',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                padding: '2px 6px',
                borderRadius: 4,
                fontFamily: 'var(--font-body)',
              }}
            >
              Limpiar todo
            </button>
          )}
          {/* Close button — only on mobile */}
          <button
            onClick={onClose}
            aria-label="Cerrar filtros"
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--color-text-secondary)',
              padding: 2,
              display: 'flex',
            }}
            className="sidebar-close-btn"
          >
            <X size={18} />
          </button>
        </div>
      </div>

      {/* Scrollable body */}
      <div style={{ overflowY: 'auto', flex: 1, padding: '0 0 24px' }}>

        {/* Search */}
        <FilterSection title="Buscar">
          <div style={{ position: 'relative' }}>
            <Search
              size={14}
              style={{
                position: 'absolute',
                left: 10,
                top: '50%',
                transform: 'translateY(-50%)',
                color: 'var(--color-text-tertiary)',
                pointerEvents: 'none',
              }}
            />
            <input
              type="text"
              value={searchText}
              onChange={e => handleSearch(e.target.value)}
              placeholder="Título, serie..."
              style={{
                width: '100%',
                padding: '7px 10px 7px 30px',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--color-border)',
                fontSize: 13,
                fontFamily: 'var(--font-body)',
                color: 'var(--color-text-primary)',
                background: 'var(--color-surface)',
                outline: 'none',
                boxSizing: 'border-box',
              }}
            />
          </div>
        </FilterSection>

        {/* Only limited toggle */}
        <FilterSection title="Tipo">
          <label
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              cursor: 'pointer',
              fontSize: 13,
              color: 'var(--color-text-primary)',
            }}
          >
            <input
              type="checkbox"
              checked={current.only_limited ?? false}
              onChange={e => updateParam('only_limited', e.target.checked ? 'true' : null)}
              style={{ accentColor: 'var(--color-primary)', width: 14, height: 14 }}
            />
            Solo ediciones limitadas / especiales
          </label>
        </FilterSection>

        {/* Signal types */}
        {facets.signalTypes.length > 0 && (
          <FilterSection title="Características">
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {facets.signalTypes.slice(0, SIGNAL_DISPLAY_LIMIT).map(({ value }) => {
                const active = current.signal_types?.includes(value) ?? false
                return (
                  <button
                    key={value}
                    onClick={() => toggleArrayParam('signal_types', value)}
                    style={{
                      background: 'none',
                      border: 'none',
                      cursor: 'pointer',
                      padding: 0,
                      outline: active ? '2px solid var(--color-primary)' : 'none',
                      outlineOffset: 2,
                      borderRadius: 999,
                    }}
                    aria-pressed={active}
                    title={value}
                  >
                    <SignalChip signal={value} size="sm" />
                  </button>
                )
              })}
            </div>
          </FilterSection>
        )}

        {/* Countries */}
        {facets.countries.length > 0 && (
          <FilterSection title="País">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {facets.countries.slice(0, 10).map(({ value, count }) => {
                const active = current.country?.includes(value) ?? false
                return (
                  <CheckRow
                    key={value}
                    active={active}
                    count={count}
                    onClick={() => toggleArrayParam('country', value)}
                  >
                    <CountryFlag country={value} showLabel />
                  </CheckRow>
                )
              })}
            </div>
          </FilterSection>
        )}

        {/* Languages */}
        {facets.languages.length > 0 && (
          <FilterSection title="Idioma">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {facets.languages.slice(0, 8).map(({ value, count }) => {
                const active = current.language?.includes(value) ?? false
                return (
                  <CheckRow
                    key={value}
                    active={active}
                    count={count}
                    label={value}
                    onClick={() => toggleArrayParam('language', value)}
                  />
                )
              })}
            </div>
          </FilterSection>
        )}

        {/* Publishers — top 12 */}
        {facets.publishers.length > 0 && (
          <FilterSection title="Editorial">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {facets.publishers.slice(0, 12).map(({ value, count }) => {
                const active = current.publisher?.includes(value) ?? false
                return (
                  <CheckRow
                    key={value}
                    active={active}
                    count={count}
                    label={value}
                    onClick={() => toggleArrayParam('publisher', value)}
                  />
                )
              })}
            </div>
          </FilterSection>
        )}

      </div>

    </div>
  )

  return (
    <>
      {/* Desktop: always visible sticky sidebar */}
      <aside
        className="sidebar-desktop"
        style={{
          width: 'var(--sidebar-width)',
          flexShrink: 0,
          borderRight: '1px solid var(--color-border)',
          background: 'var(--color-surface)',
          position: 'sticky',
          top: 'var(--header-height)',
          height: 'calc(100vh - var(--header-height))',
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {content}
      </aside>

      {/* Mobile: slide-over drawer */}
      {isOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 200,
            display: 'flex',
          }}
          className="sidebar-mobile-overlay"
        >
          {/* Backdrop */}
          <div
            onClick={onClose}
            style={{
              position: 'absolute',
              inset: 0,
              background: 'rgba(0,0,0,0.4)',
            }}
          />
          {/* Drawer */}
          <div
            style={{
              position: 'relative',
              width: 'min(320px, 90vw)',
              background: 'var(--color-surface)',
              height: '100%',
              overflowY: 'auto',
              zIndex: 1,
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            {content}
          </div>
        </div>
      )}

    </>
  )
}

function FilterSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ padding: '14px 16px 0' }}>
      <p
        style={{
          fontSize: 10,
          fontWeight: 600,
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
          color: 'var(--color-text-tertiary)',
          marginBottom: 8,
        }}
      >
        {title}
      </p>
      {children}
    </div>
  )
}

function CheckRow({
  active,
  count,
  label,
  children,
  onClick,
}: {
  active: boolean
  count: number
  label?: string
  children?: React.ReactNode
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        width: '100%',
        background: active ? 'var(--color-primary-subtle)' : 'none',
        border: 'none',
        borderRadius: 'var(--radius-xs)',
        cursor: 'pointer',
        padding: '4px 6px',
        fontSize: 13,
        color: active ? 'var(--color-primary)' : 'var(--color-text-primary)',
        fontFamily: 'var(--font-body)',
        textAlign: 'left',
      }}
      aria-pressed={active}
    >
      <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        <span
          style={{
            width: 14,
            height: 14,
            borderRadius: 3,
            border: `1.5px solid ${active ? 'var(--color-primary)' : 'var(--color-border)'}`,
            background: active ? 'var(--color-primary)' : 'transparent',
            flexShrink: 0,
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          {active && (
            <svg width="9" height="7" viewBox="0 0 9 7" fill="none">
              <path d="M1 3L3.5 5.5L8 1" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          )}
        </span>
        {children ?? label}
      </span>
      <span style={{ fontSize: 11, color: 'var(--color-text-tertiary)' }}>
        {count.toLocaleString('es')}
      </span>
    </button>
  )
}

export default SidebarFilters
