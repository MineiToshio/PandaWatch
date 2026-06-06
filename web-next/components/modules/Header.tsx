// Server Component — no "use client"
import { Suspense } from 'react'
import Link from 'next/link'
import { SearchBar } from './SearchBar'

export function Header() {
  return (
    <header
      style={{
        position: 'sticky',
        top: 0,
        zIndex: 100,
        background: '#fff',
        borderBottom: '1px solid var(--ink-200)',
        boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
        height: 'var(--header-height)',
        display: 'flex',
        alignItems: 'center',
        padding: '0 24px',
        gap: 16,
      }}
    >
      {/* Logo: panda mark + wordmark */}
      <Link
        href="/"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          textDecoration: 'none',
          flexShrink: 0,
        }}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/panda-mark.png"
          width={32}
          height={32}
          alt="PandaWatch"
          style={{ flexShrink: 0, display: 'block', objectFit: 'contain' }}
        />
        <span
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 17,
            letterSpacing: '-0.02em',
          }}
        >
          <span style={{ fontWeight: 600, color: 'var(--color-text-primary)' }}>Panda</span>
          <span style={{ fontWeight: 400, color: 'var(--color-primary)' }}>Watch</span>
        </span>
      </Link>

      {/* Search bar — Client Component (useSearchParams) wrapped in Suspense so pages
          with static prerendering (item/edition/series) don't bail out at build. */}
      <Suspense fallback={<div style={{ flex: 1 }} />}>
        <SearchBar />
      </Suspense>
    </header>
  )
}

export default Header
