'use client'

import { useState } from 'react'
import type { Facets, FilterParams, SortKey } from '@/lib/types'
import { SidebarFilters } from './SidebarFilters'
import { SortBar } from './SortBar'

type CatalogControlsProps = {
  facets: Facets
  current: FilterParams
  total: number
  sort: SortKey
  page: number
  pages: number
  children: React.ReactNode
}

export function CatalogControls({
  facets,
  current,
  total,
  sort,
  page,
  pages,
  children,
}: CatalogControlsProps) {
  const [drawerOpen, setDrawerOpen] = useState(false)

  return (
    <div
      style={{
        display: 'flex',
        minHeight: 'calc(100vh - var(--header-height))',
        alignItems: 'flex-start',
      }}
    >
      <SidebarFilters
        facets={facets}
        current={current}
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      />

      <div
        style={{
          flex: 1,
          minWidth: 0,
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <SortBar
          total={total}
          sort={sort}
          page={page}
          pages={pages}
          onOpenFilters={() => setDrawerOpen(true)}
        />
        {children}
      </div>
    </div>
  )
}

export default CatalogControls
