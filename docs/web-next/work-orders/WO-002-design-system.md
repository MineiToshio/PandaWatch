# WO-002: Design System Implementation

**Phase:** 1  
**Effort:** M  
**Status:** Done (corrección aplicada: globals.css usa los tokens bamboo/ink del handoff PandaWatch, no los OKLCH de PandaTrack). Nota 2026-06-12: components/core/ se eliminó por ser código muerto — los componentes reales viven en modules/catalog/item/series/edition.  
**Related:** [FRD-002](../FRD-002-design-system.md), [BP-004](../blueprints/BP-004-component-hierarchy.md)  
**Prerequisites:** WO-001 (project scaffold)

---

## Objective

Implement the **PandaWatch Design System** in the Next.js app.
Source of truth: the Claude Design handoff bundle — `project/colors_and_type.css` and
the JSX components in `project/ui_kits/pandawatch/`.

The previous implementation (done before the handoff bundle was reviewed) used the wrong
design system (pink OKLCH tokens from PandaTrack, dark mode, system-ui font). All of that
must be replaced.

---

## Context: What the Real Design System Looks Like

Read `docs/app/FRD-002-design-system.md` for the full spec. Key points:

- **Colors:** Hex values, no OKLCH. Primary = Bamboo Green `#1A8A5A`. Background = warm
  paper `#F5F1EB`. Surface = white `#FFFFFF`.
- **Typography:** Google Fonts — Space Grotesk (headings) + DM Sans (body) + JetBrains Mono (mono).
- **No dark mode.** Light theme only. Remove all `data-theme` and ThemeToggle logic.
- **No emoji.** Lucide icons only (size 16 or 20 in UI contexts).
- **Rarity levels:** Accessible / Limited / Rare / Super Rare / Ultra Rare / Unknown.
  (Note: 4th level is "Super Rare", not "Very Rare".)

---

## Tasks

### Task 1: Rewrite `globals.css`

File: `web-next/app/globals.css`

Replace the current OKLCH/pink/dark-mode CSS with the real token system.

Structure:
1. `@import "tailwindcss";`
2. Google Fonts `@import url(...)` for Space Grotesk, DM Sans, JetBrains Mono
3. `:root { }` block with ALL tokens from `colors_and_type.css`:
   - Font families (`--font-display`, `--font-body`, `--font-mono`)
   - Bamboo scale (`--bamboo-50` through `--bamboo-900`)
   - Vermillion scale (`--vermillion-50` through `--vermillion-900`)
   - Ink scale (`--ink-50` through `--ink-900`)
   - Rarity tokens (`--rarity-accessible-fg/bg/border`, ..., `--rarity-unknown-fg/bg/border`)
   - Status colors (`--status-new-fg/bg`, `--status-changed-fg/bg`)
   - Semantic aliases (`--color-bg`, `--color-surface`, `--color-border`, `--color-primary`, etc.)
   - Focus ring (`--color-focus-ring`)
   - Shadows (`--shadow-sm`, `--shadow-md`, `--shadow-lg`, `--shadow-xl`)
   - Radius (`--radius-xs` through `--radius-full`)
   - Spacing (`--space-1` through `--space-24`)
   - Typography scale (`--text-display-2xl` through `--text-2xs`)
   - Line heights, letter spacing, font weights
   - Animation tokens
   - Layout tokens (`--max-width`, `--sidebar-width`, `--header-height`)
4. Semantic type classes (`.pw-h1` through `.pw-mono`)
5. Global base styles (`*`, `html`, `body`, `:focus-visible`, scrollbar)
6. `@theme inline { }` bridge for Tailwind — map `--color-*` tokens

**No dark mode block.** Remove `:root[data-theme="dark"]` entirely.

The card stack effect for collection cards (`.edition-card[data-leaves]`) can stay
if it follows the real design system token names.

### Task 2: Fix `layout.tsx`

File: `web-next/app/layout.tsx`

```tsx
import type { Metadata } from 'next'
import './globals.css'
import { Header } from '@/components/modules/Header'

export const metadata: Metadata = {
  title: 'PandaWatch',
  description: 'Find special manga editions before they disappear',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;1,9..40,400&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <Header />
        {children}
      </body>
    </html>
  )
}
```

Changes from current: remove `data-theme="light"`, remove anti-FODT script, add Google
Fonts preconnect + stylesheet, change description to English, change lang to `"en"`.

### Task 3: Copy panda mark asset + rewrite `Header`

**3a. Copy the asset (one-time):**

```bash
cp /tmp/design_bundle/pandawatch-design-system/project/assets/panda-mark.png \
   web-next/public/panda-mark.png
```

The image is a ~2 MB transparent PNG of the illustrated panda + magnifying glass mark from
chats 1–3. Lives in `public/`, served at `/panda-mark.png`.

**3b. Header component**

File: `web-next/components/modules/Header.tsx`

The header is a **Server Component** (no `"use client"`). No ThemeToggle.

Design spec (from `Header.jsx` in the bundle):
- Background: `#FFFFFF`, border-bottom: `1px solid #E5E0D8` (`--ink-200`)
- Shadow: `0 1px 3px rgba(0,0,0,0.04)`
- Height: 60px, sticky top-0
- Left: `<img src="/panda-mark.png" width="32" height="32">` + wordmark
  "**Panda**Watch" — "Panda" semibold ink-black `#1C1915`, "Watch" regular `#1A8A5A`,
  17px Space Grotesk, letter-spacing `-0.02em`, gap 8px between mark and wordmark.
- Center: Search bar — warm background `#F5F1EB` when unfocused, white + green border + green ring when focused.
- Right: "Filters" button slot — skip for now (catalog-scoped, added in WO-004).
- No ThemeToggle, no dark mode toggle.

```tsx
// Server Component — no "use client"
import { SearchBar } from './SearchBar'

export function Header() {
  return (
    <header style={{
      position: 'sticky', top: 0, zIndex: 100,
      background: '#fff', borderBottom: '1px solid var(--ink-200)',
      boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
      height: 'var(--header-height)',
      display: 'flex', alignItems: 'center',
      padding: '0 24px', gap: 16,
    }}>
      <a href="/" style={{ display: 'flex', alignItems: 'center', gap: 8, textDecoration: 'none', flexShrink: 0 }}>
        <img src="/panda-mark.png" width={32} height={32} alt="PandaWatch"
             style={{ flexShrink: 0, display: 'block', objectFit: 'contain' }} />
        <span style={{ fontFamily: 'var(--font-display)', fontSize: 17, letterSpacing: '-0.02em' }}>
          <span style={{ fontWeight: 600, color: 'var(--color-text-primary)' }}>Panda</span>
          <span style={{ fontWeight: 400, color: 'var(--color-primary)' }}>Watch</span>
        </span>
      </a>
      <SearchBar />
    </header>
  )
}
```

The search input needs `"use client"` for focus state — extract it as `SearchBar.tsx`
(Client Component) and import it in the server Header.

### Task 4: Delete or stub `ThemeToggle`

File: `web-next/components/modules/ThemeToggle.tsx`

No dark mode in this design system. Either delete the file, or replace with a null stub
so any existing imports don't break:

```tsx
// ThemeToggle.tsx — stub (dark mode not implemented)
export function ThemeToggle() { return null }
export default ThemeToggle
```

Remove the `ThemeToggle` import from `Header.tsx`.

### Task 5: Rewrite `Button` component

File: `web-next/components/core/Button/buttonVariants.ts`

Replace all OKLCH references with real design system tokens:

- `primary`: `background: var(--color-primary)` (`#1A8A5A`), hover: `var(--color-primary-hover)` (`#147047`)
- `secondary`: neutral surface with border
- Focus ring: `var(--color-focus-ring)` (`rgba(26,138,90,0.45)`)
- Remove any `var(--accent)` / OKLCH references
- Keep CVA structure; update class names / inline styles to use real tokens

### Task 6: Rewrite `Chip` component

File: `web-next/components/core/Chip.tsx`

Replace `color-mix(in oklch, ...)` with explicit hex colors from the real token set.
Map variant → token:

| Variant | Foreground | Background | Border |
|---|---|---|---|
| `accent` (bamboo/primary) | `#1A8A5A` | `#EDFAF3` | `#A6DFCA` |
| `neutral` | `var(--ink-600)` | `var(--ink-100)` | `var(--ink-200)` |
| `info` (indigo/rare) | `#2D52CC` | `#EEF2FF` | `#C7D2FE` |
| `success` | `#1A8A5A` | `#EDFAF3` | `#A6DFCA` |
| `warning` | `#9E6C00` | `#FFFBEB` | `#FDE68A` |
| `destructive` | `#D93D1A` | `#FEF3EF` | `#FABEAD` |

### Task 7: Add `RarityBadge` component

File: `web-next/components/core/RarityBadge.tsx`

This is the most important PandaWatch-specific component. See FRD-002 FR-3 for full spec.

```tsx
type RarityLevel = 'accessible' | 'limited' | 'rare' | 'super-rare' | 'ultra-rare' | 'unknown'

const RARITY_CONFIG: Record<RarityLevel, {
  label: string
  fg: string
  bg: string
  border: string
  icon: 'Circle' | 'Star' | 'Sparkles' | 'Gem' | 'Diamond' | 'HelpCircle'
  tooltip: string
}> = {
  'accessible':  { label: 'Accessible', fg: '#64748B', bg: '#F1F5F9', border: '#CBD5E1', icon: 'Circle',    tooltip: 'Available edition, not hard to find' },
  'limited':     { label: 'Limited',    fg: '#1A8A5A', bg: '#EDFAF3', border: '#A6DFCA', icon: 'Star',      tooltip: 'Limited print, harder to track down' },
  'rare':        { label: 'Rare',       fg: '#2D52CC', bg: '#EEF2FF', border: '#C7D2FE', icon: 'Sparkles',  tooltip: 'Rare — usually requires secondary market' },
  'super-rare':  { label: 'Super Rare', fg: '#7C3AED', bg: '#F5F3FF', border: '#DDD6FE', icon: 'Gem',       tooltip: 'Very limited print run or regional exclusive' },
  'ultra-rare':  { label: 'Ultra Rare', fg: '#9E6C00', bg: '#FFFBEB', border: '#FDE68A', icon: 'Diamond',   tooltip: 'Extremely rare — event, lottery, or near-unique' },
  'unknown':     { label: 'Unknown',    fg: '#9CA3AF', bg: '#F9FAFB', border: '#E5E7EB', icon: 'HelpCircle', tooltip: 'Rarity estimated from signals, source and availability' },
}

export function scoreToRarity(score: number | null | undefined): RarityLevel {
  if (score == null) return 'unknown'
  if (score >= 86) return 'ultra-rare'
  if (score >= 66) return 'super-rare'
  if (score >= 41) return 'rare'
  if (score >= 21) return 'limited'
  return 'accessible'
}
```

Display modes: `mode="light"` (default) uses bg/border/fg; `mode="glassy"` for on-cover use
(`background: rgba(20,17,14,0.82)`, `backdrop-filter: blur(6px)`, border
`1px solid rgba(255,255,255,0.12)`).

Shape: **rounded rectangle, not pill.** Per-size values (must match the bundle's
`MangaCard.jsx`):

| Size | Radius | Padding | Font size | Icon size | Gap |
|---|---|---|---|---|---|
| `sm` | 5px | `4px 8px` | 10px | 9px | 4px |
| `md` | 5px | `4px 9px` | 11px | 12px | 5px |
| `lg` | 7px | `6px 12px` | 13px | 14px | 6px |

Font family: `var(--font-display)` (Space Grotesk), weight 600,
`white-space: nowrap` so "Ultra Rare" / "Super Rare" never wrap.

### Task 8: Fix `SignalChip` — remove emoji

File: `web-next/components/modules/SignalChip.tsx`

The design system explicitly forbids emoji in UI. Replace all emoji icons with Lucide icons.

Example mapping:
```ts
limited:         { icon: Star,       label: 'Limited Edition',   chipVariant: 'accent' },
special_edition: { icon: Sparkles,   label: 'Special Edition',   chipVariant: 'accent' },
box_set:         { icon: Package,    label: 'Box Set',           chipVariant: 'info' },
variant_cover:   { icon: Layers,     label: 'Variant Cover',     chipVariant: 'neutral' },
artbook:         { icon: BookOpen,   label: 'Artbook',           chipVariant: 'info' },
deluxe:          { icon: Gem,        label: 'Deluxe',            chipVariant: 'accent' },
hardcover:       { icon: BookOpen,   label: 'Hardcover',         chipVariant: 'neutral' },
kanzenban:       { icon: Layers,     label: 'Kanzenban',         chipVariant: 'info' },
bonus:           { icon: Package,    label: 'With Extra',        chipVariant: 'success' },
retailer_exclusive: { icon: Globe,   label: 'Store Exclusive',   chipVariant: 'warning' },
```

Use `<Icon icon={Star} size="sm" />` from the `Icon` component.

### Task 9: Verify visually

Run `npm run dev`. Check against the design system reference:
- Page background is warm paper (`#F5F1EB`), not white
- Header: white background, bamboo green "Watch" in wordmark
- Google Fonts loading (Space Grotesk visible in any heading)
- Primary button is green, not pink
- No dark mode toggle visible anywhere
- `npm run build` passes with no TypeScript errors

---

## Files Modified

- `web-next/public/panda-mark.png` — **copied** from design bundle (new asset)
- `web-next/app/globals.css` — complete rewrite
- `web-next/app/layout.tsx` — Google Fonts, remove dark mode
- `web-next/components/modules/Header.tsx` — real design, panda mark img, no ThemeToggle
- `web-next/components/modules/SearchBar.tsx` — Client Component split out of Header
- `web-next/components/modules/ThemeToggle.tsx` — stub (returns null)
- `web-next/components/core/Button/buttonVariants.ts` — bamboo green primary
- `web-next/components/core/Chip.tsx` — real hex colors
- `web-next/components/core/RarityBadge.tsx` — rounded-rect shape (NOT pill), bundle sizes
- `web-next/components/modules/SignalChip.tsx` — Lucide icons, no emoji

---

## Acceptance Criteria

- [ ] `npm run build` passes with zero TypeScript errors
- [ ] Page background is `#F5F1EB` (not white, not pink)
- [ ] Header shows the panda PNG at 32×32 to the left of the wordmark
- [ ] Header wordmark: bold "Panda" ink-black + regular "Watch" bamboo green
- [ ] Google Fonts load correctly (Space Grotesk in headings)
- [ ] `<RarityBadge score={90} />` renders Ultra Rare amber **rounded-rect** with Diamond icon (NOT pill-shaped)
- [ ] `<RarityBadge score={75} />` renders Super Rare violet rounded-rect with Gem icon
- [ ] `<Button variant="primary">` is bamboo green (not pink, not purple)
- [ ] No emoji anywhere in rendered UI (CountryFlag's per-country flag is the only documented exception)
- [ ] No ThemeToggle / dark mode controls anywhere
