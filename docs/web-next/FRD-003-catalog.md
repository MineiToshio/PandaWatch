# FRD-003: Catalog Page

**Version:** 1.0  
**Status:** Draft  
**Author:** Architecture session 2026-05-27  
**Related:** [BP-002](blueprints/BP-002-url-routing.md), [BP-004](blueprints/BP-004-component-hierarchy.md), [WO-004](work-orders/WO-004-catalog.md)

---

## Overview

The catalog page (`/`) is the main landing view. It displays all manga special
editions as cards, grouped by edition (same series + publisher + edition type),
with a sidebar for filtering and a top bar for sorting and pagination.

This is the direct port of the Alpine.js "catalog" view from `web/index.html`.

---

## Problem Statement

The Alpine.js catalog loads ~3 MB of JSON, runs all grouping client-side, and
has no shareable filter state (filters are not in the URL). This means:
- Slow initial load for new visitors
- No deep-linking to filtered views ("show me only Japanese box sets")
- Not indexable by search engines

The Next.js catalog page is server-rendered with filter state in URL search params,
making every filter combination a shareable, bookmarkable, crawlable URL.

---

## User Stories

- As a **collector**, I want to browse all manga special editions in one view.
- As a **collector looking for Japanese box sets**, I want to filter by country=JP
  and signal_type=box_set and share the URL with a friend.
- As a **returning visitor**, I want my scroll position and filters to survive
  a page refresh (preserved in URL params).
- As a **mobile user**, I want a compact layout that doesn't require horizontal scrolling.

---

## Functional Requirements

### FR-1: Page layout

Two-column layout:
- **Left sidebar** (fixed width 280px on desktop, collapsible drawer on mobile):
  All filter controls.
- **Main area** (flex-1): Sort bar + edition grid + pagination.

On mobile (< 768px): sidebar slides in from left as a drawer, triggered by a
"Filtros" button in the top bar.

### FR-2: Edition card grid

Display `Cluster[]` as a responsive grid:
- Desktop (≥ 1280px): 5 columns
- Laptop (≥ 1024px): 4 columns
- Tablet (≥ 768px): 3 columns
- Mobile (≥ 480px): 2 columns
- Small mobile: 1 column

Each card shows:
- **Cover image** — `image_local` via `/images/{filename}` → `image_url` remote
  fallback → 📚 emoji placeholder
- **Stack effect** — CSS leaves behind the card: 1 leaf if 1 item, 2 leaves if 2–4
  items, 3 leaves if 5+ items in the cluster
- **Title** — `canonical.series_display` or `canonical.title`
- **Edition label** — `canonical.edition_display`
- **Volume count badge** — "3 tomos" if more than 1 volume
- **Country flag** emoji + publisher name
- **Score badge** — color-coded
- **Signal type chips** — up to 3, overflow as "+N más"
- **Hover state** — slight lift (`-translate-y-1`) + shadow elevation change

Clicking a card navigates to `/edition/[editionKey]` if the cluster has an
`edition_key`, or `/item/[slug]` directly if it's a standalone item (no edition).

### FR-3: Sidebar filters

All filters update the URL via `router.replace()`. The page Server Component reads
`searchParams` and re-renders with the new filter state.

| Filter | Type | UI Control |
|---|---|---|
| Search | text | Input with 🔍 icon, debounce 300ms |
| Country | multi-select | Checkbox list with country flag emoji + count |
| Language | multi-select | Checkbox list with count |
| Publisher | multi-select | Checkbox list with count (collapsed to top 8 + "ver más") |
| Product type | multi-select | Checkbox list |
| Source class | multi-select | Checkbox list (official / curated / community / unknown) |
| Signal types | multi-chip | `Chip` row, click to toggle; multiple selection = AND filter |
| Min score | range slider | 0–300, label shows current value |
| Solo limitadas | toggle | Shortcut for `signal_types ⊇ {limited, special_edition, ...}` |

**Active filter summary:** When any filter is active, a "Limpiar filtros" link
appears below the title. Each active filter shows as a dismissible tag.

**Facet counts** in the sidebar show the count from the **unfiltered** corpus
(not dynamic — stable counts regardless of other active filters).

### FR-4: Sort bar

Located above the grid:

```
Showing 847 ediciones    [Sort: Mejor puntuación ▾]    [Page: < 1 2 3 ... 14 >]
```

Sort options (select dropdown):
- Mejor puntuación (score desc) — default
- Menor puntuación (score asc)
- Más recientes (date desc)
- Más antiguos (date asc)
- Título A→Z
- Título Z→A

### FR-5: Pagination

- 60 items per page
- URL param: `?page=N`
- Visible page window: current ± 2, always first/last, ellipsis when gap > 1
- "Showing X–Y of Z ediciones" counter

### FR-6: Filter state in URL

All filter state is encoded in URL search params:

```
/?q=berserk&country=JP&country=FR&signal_types=box_set&min_score=100&sort=date_desc&page=2
```

Arrays use repeated params (`country=JP&country=FR`).
Default values are not written to the URL (clean URLs).

### FR-7: Empty state

When filters produce 0 results:
- Friendly message: "No encontramos ediciones con estos filtros."
- "Limpiar todos los filtros" button
- Suggestion: show the 3 most recently added items as "Quizás te interese"

---

## Non-Functional Requirements

- **SEO:** The catalog page is server-rendered. Search engines see the full grid.
  `<title>` and `<meta description>` are set from the server.
- **Performance:** First Contentful Paint < 1s on localhost. The grid is server-rendered
  HTML — no hydration needed for the cards themselves.
- **Accessibility:** Filter controls are properly labeled. Grid has `role="list"`.
  Keyboard navigation works for filters and cards.

---

## Out of Scope

- Infinite scroll (use pagination instead — better for URL state)
- "Saved filters" / user preferences (no auth yet)
- Map view or calendar view of releases

---

## Acceptance Criteria

- [ ] Catalog loads and displays cards for all clusters in items.jsonl
- [ ] Stack CSS shows 1/2/3 leaves correctly based on cluster size
- [ ] Search for "berserk" returns only Berserk items
- [ ] Filtering by country=JP shows Japanese items only
- [ ] Selecting signal_type chip "box_set" AND "limited" filters to items with BOTH
- [ ] URL changes when any filter is applied
- [ ] Pasting a filter URL in a new tab shows the same filtered results
- [ ] "Limpiar filtros" resets to `/?` and shows all items
- [ ] Pagination works and URL has correct `?page=N`
- [ ] Mobile: sidebar accessible via drawer

---

## Dependencies

- FRD-001 (data layer) — `loadClusters()`, `filterClusters()`, `buildFacets()`
- FRD-002 (design system) — Button, Chip, Badge, Typography
- FRD-006 (slug generation) — needed only for card click navigation
