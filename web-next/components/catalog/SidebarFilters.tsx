'use client'

import { useEffect, useRef } from 'react'
import { X } from 'lucide-react'
import type { Facets, FilterParams } from '@/lib/types'
import { SignalChip } from '@/components/modules/SignalChip'
import { CountryFlag } from '@/components/modules/CountryFlag'
import { SearchBar } from '@/components/modules/SearchBar'
import { RARITY_META, RARITY_VALUES } from '@/components/modules/RarityBadge'
import { PRODUCT_TYPE_LABELS } from '@/lib/format'
import { useCatalogParams } from '@/lib/useCatalogParams'

type SidebarFiltersProps = {
  facets: Facets
  current: FilterParams
  isOpen: boolean
  onClose: () => void
}

const SIGNAL_DISPLAY_LIMIT = 8

export function SidebarFilters({ facets, current, isOpen, onClose }: SidebarFiltersProps) {
  // Mutación de URL centralizada (auditoría #11) — antes reimplementada acá
  // con matices propios (leía window.location.search a propósito). isPending
  // (useTransition) da feedback discreto mientras el catálogo re-renderiza
  // (auditoría #7).
  const { isPending, set, toggle, clearAll } = useCatalogParams()
  const dialogRef = useRef<HTMLDialogElement>(null)

  // Drawer móvil vía <dialog>.showModal(): focus trap + Escape + backdrop
  // gratis, sin dependencia (auditoría #13) — antes Tab se escapaba del
  // drawer hacia la página de fondo pese a aria-modal="true".
  useEffect(() => {
    const dlg = dialogRef.current
    if (!dlg) return
    if (isOpen && !dlg.open) dlg.showModal()
    if (!isOpen && dlg.open) dlg.close()
  }, [isOpen])

  // showModal() ya bloquea la interacción con el fondo, pero no el scroll
  // táctil en iOS Safari — se sigue bloqueando el body explícitamente.
  useEffect(() => {
    if (!isOpen) return
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = ''
    }
  }, [isOpen])

  // Click en el backdrop (el área del <dialog> fuera del panel de contenido)
  // cierra — <dialog> no lo hace por default, sólo Escape.
  function handleBackdropClick(e: React.MouseEvent<HTMLDialogElement>) {
    if (e.target === dialogRef.current) onClose()
  }

  function updateParam(key: string, value: string | null) {
    set(key, value)
  }

  function toggleArrayParam(key: string, value: string) {
    toggle(key, value)
  }

  function handleClearAll() {
    // El orden elegido no es un filtro — se conserva
    clearAll({ keepSort: true })
    onClose()
  }

  // Incluye product_type/source_class (auditoría #21 — antes "Limpiar todo"
  // no aparecía si esos filtros llegaban por URL, pese a que filterClusters
  // ya los aplica).
  const hasActiveFilters =
    !!current.q ||
    (current.country?.length ?? 0) > 0 ||
    (current.language?.length ?? 0) > 0 ||
    (current.signal_types?.length ?? 0) > 0 ||
    (current.rarity?.length ?? 0) > 0 ||
    (current.publisher?.length ?? 0) > 0 ||
    (current.product_type?.length ?? 0) > 0 ||
    (current.source_class?.length ?? 0) > 0 ||
    current.only_limited

  const content = (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        opacity: isPending ? 0.7 : 1,
        transition: 'opacity 120ms',
      }}
    >
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
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            fontSize: 13,
            fontWeight: 600,
            fontFamily: 'var(--font-display)',
            color: 'var(--color-text-primary)',
          }}
        >
          Filtros
          {isPending && <span className="pw-spinner" aria-hidden="true" />}
        </span>
        <div style={{ display: 'flex', gap: 8 }}>
          {hasActiveFilters && (
            <button
              onClick={handleClearAll}
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

        {/* Search — SOLO en el drawer móvil. En desktop el buscador del
            header ya cubre el caso; tener dos cajas de búsqueda visibles a
            la vez era doble superficie de bugs (auditoría #16). Misma
            implementación (SearchBar) que el header — mismo debounce. */}
        <div className="sidebar-search-mobile-only">
          <FilterSection title="Buscar">
            <SearchBar />
          </FilterSection>
        </div>

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

        {/* Rarity */}
        <FilterSection title="Rareza">
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {RARITY_VALUES.map(value => {
              const { label, color, icon } = RARITY_META[value]
              const active = current.rarity?.includes(value) ?? false
              return (
                <button
                  key={value}
                  onClick={() => toggleArrayParam('rarity', value)}
                  aria-pressed={active}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 5,
                    padding: '5px 10px',
                    borderRadius: 6,
                    fontSize: 11,
                    fontWeight: 600,
                    fontFamily: 'var(--font-display)',
                    cursor: 'pointer',
                    border: active
                      ? `1.5px solid ${color}`
                      : '1.5px solid var(--color-border)',
                    background: active ? `${color}18` : 'var(--color-surface)',
                    color: active ? color : 'var(--color-text-secondary)',
                    transition: 'all 120ms',
                  }}
                >
                  {icon}
                  {label}
                </button>
              )
            })}
          </div>
        </FilterSection>

        {/* Product type (auditoría #21 — filtro que ya soportaba filterClusters
            pero no tenía UI; labels desde format.ts) */}
        {facets.productTypes && facets.productTypes.length > 0 && (
          <FilterSection title="Tipo de producto">
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {facets.productTypes.map(({ value, count }) => {
                const active = current.product_type?.includes(value) ?? false
                return (
                  <button
                    key={value}
                    onClick={() => toggleArrayParam('product_type', value)}
                    aria-pressed={active}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 5,
                      padding: '5px 10px',
                      borderRadius: 6,
                      fontSize: 11,
                      fontWeight: 600,
                      fontFamily: 'var(--font-display)',
                      cursor: 'pointer',
                      border: active
                        ? '1.5px solid var(--color-primary)'
                        : '1.5px solid var(--color-border)',
                      background: active ? 'var(--color-primary-subtle)' : 'var(--color-surface)',
                      color: active ? 'var(--color-primary)' : 'var(--color-text-secondary)',
                      transition: 'all 120ms',
                    }}
                  >
                    {PRODUCT_TYPE_LABELS[value] ?? value}
                    <span className="pw-check-row-count">{count.toLocaleString('es')}</span>
                  </button>
                )
              })}
            </div>
          </FilterSection>
        )}

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
              {/* Sin límite: son ~14 países y recortar deja filtros inalcanzables */}
              {facets.countries.map(({ value, count }) => {
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

      {/* Mobile: <dialog> slide-over drawer (auditoría #13) */}
      <dialog
        ref={dialogRef}
        className="pw-drawer-dialog"
        aria-label="Filtros"
        onClose={onClose}
        onClick={handleBackdropClick}
      >
        {/* stopPropagation: un click DENTRO del panel no debe burbujear al
            <dialog> y disparar el cierre por "click en backdrop". */}
        <div
          onClick={e => e.stopPropagation()}
          style={{ height: '100%', display: 'flex', flexDirection: 'column' }}
        >
          {content}
        </div>
      </dialog>
    </>
  )
}

function FilterSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="pw-filter-section">
      <p className="pw-filter-title">{title}</p>
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
    <button className="pw-check-row" onClick={onClick} aria-pressed={active}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        <span className="pw-check-row-box">
          {active && (
            <svg width="9" height="7" viewBox="0 0 9 7" fill="none">
              <path d="M1 3L3.5 5.5L8 1" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          )}
        </span>
        {children ?? label}
      </span>
      <span className="pw-check-row-count">{count.toLocaleString('es')}</span>
    </button>
  )
}

export default SidebarFilters
