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
- Mobile-wide (≥ 480px): 3 columns
- Mobile: 2 columns

> **Implementation note:** columns must use `repeat(N, minmax(0, 1fr))`, NOT `repeat(N, 1fr)`.
> The `1fr` shorthand expands to `minmax(auto, 1fr)` — columns cannot shrink below minimum
> content size. Cards have `whiteSpace: nowrap` text that forces ~258px minimum, causing
> horizontal overflow. `minmax(0, 1fr)` + `min-width: 0` on `.edition-card` removes that floor.

Each card shows:
- **Cover image** — `image_local` via `/images/{filename}` → `image_url` remote
  fallback → 📚 emoji placeholder. The remote `<img>` fallback uses
  `position:absolute; inset:0` when `fill` so it fills the container like the
  Next.js `<Image>` it replaces.
- **Stack effect** — driven by `data-leaves="1|2|3"` on `.edition-card`
  (1 leaf if 1 item, 2 if 2–4, 3 if 5+). Rendered with CSS `box-shadow`
  (NOT `::before`/`::after` pseudo-elements). Box-shadows follow the card's
  `border-radius` automatically and **do not affect layout size**, so a
  stacked card occupies the same grid cell as a single card — see the
  uniform-height note below.
- **Rarity badge** (top-left, glassy mode) — `RarityBadge` with
  `background: rgba(20,17,14,0.82)` + `backdrop-filter: blur(6px)`. Hidden
  when `rarity` is absent. Uses bright-on-dark foreground colors per tier.
- **Title** — `canonical.series_display` or `canonical.title`
- **Edition label** — `canonical.edition_display`
- **Volume count badge** — "3 tomos" if more than 1 volume
- **Country flag** emoji + publisher name
- **Edition type chip** (2026-06-12) — `EditionTypeChip`, tipo de edición
  derivado del slug del `edition_key` (label ES: "Edición especial",
  "Kanzenban", "Box Set"…; omitido para `regular`). Desde la política de
  títulos el title oficial ya no lleva el tipo inyectado — este chip lo
  comunica. Señales equivalentes se dedupean (no "Box Set Box Set").
- **Signal type chips** — hasta 2 chips totales en la fila: con chip de
  edición entra 1 signal, sin él entran 2; single row (`flex-wrap: nowrap` +
  `overflow: hidden`); remaining count rendered as "+N". Single-row clip is
  intentional to preserve uniform card height.
- **Hover state** — slight lift (`-translate-y-1`) + shadow elevation change

**Removed:** Score badge was removed from EditionCard 2026-05-30. El score se
eliminó por completo de la UI y del ordenamiento el 2026-06-01 (saturaba ~26%
del catálogo en una sola banda, perdió sentido como ranking). El scoring interno
del pipeline (gate de coleccionables) se mantiene, pero NO es user-facing.

> **Uniform card height:** every card (single or stacked) is exactly the same
> size. The cover is a fixed `aspect-ratio: 2/3` and the info block below it has
> a **fixed height of 96px** with three reserved slots: series name (14px, always
> reserved even when empty), title (34px = up to 2 clamped lines), and a chip row
> anchored to the bottom via `margin-top: auto`. `overflow: hidden` on the info
> block guarantees nothing spills past 96px. This decouples card height from
> content length — shorter content leaves empty space at the bottom instead of
> shrinking the card. The 24px grid `gap` keeps the max box-shadow offset
> (10px×12px for `leaves=3`) comfortably within the gutter, so stacked cards
> never visually touch their neighbours.

Clicking a card navigates to `/edition/[editionKey]` only when the cluster has
an `edition_key` **and** `volumeCount > 1` (a real multi-volume edition).
Single-volume editions and standalone items go to `/item/[slug]` directly.

### FR-3: Sidebar filters

All filters update the URL via `router.replace()`. The page Server Component reads
`searchParams` and re-renders with the new filter state.

| Filter | Type | UI Control |
|---|---|---|
| Search | text | Input with 🔍 icon, debounce 600ms + Enter fires immediately. Matchea `title` + `title_original` + `series_display` + **editorial** (todas las de `c.publishers`) + **ISBN** (sin guiones) + **aliases de la serie** (`data/series_aliases.json` vía `aliasSearchIndex()`, política de títulos 2026-06-12: el título oficial no se renombra; "kimetsu no yaiba" y "guardianes de la noche" devuelven lo mismo). **Normalización + tokens AND** (auditoría Fable 2026-07-08 #1/#2): `normalize()` = lowercase + NFD + strip de diacríticos → "pokemon" matchea "Pokémon", "japon"/"Japón"; el query se tokeniza por espacios y TODOS los tokens deben aparecer ("berserk deluxe" matchea aunque los tokens no sean adyacentes en el título). Un token que parece ISBN (10-13 dígitos con/sin guiones) se colapsa a dígitos. El CJK queda intacto (substring). El texto buscable normalizado se **precomputa una vez por cluster** (`Cluster.searchText`, data layer), no por request. |
| Country | multi-select | Checkbox list with country flag emoji + count |
| Language | multi-select | Checkbox list with count |
| Publisher | multi-select | Checkbox list with count (collapsed to top 8 + "ver más") |
| Product type | multi-select | Checkbox list |
| Source class | multi-select | Checkbox list (official / curated / community / unknown) |
| Signal types | multi-chip | `Chip` row, click to toggle; multiple selection = AND filter |
| Rareza | multi-chip | Common / Rare / Super Rare / Ultra Rare |
| Solo limitadas | toggle | Shortcut for `signal_types ⊇ {limited, special_edition, ...}` |

> **Removido (2026-06-01):** el filtro "Min score" (range slider) se eliminó
> junto con el score de la UI.

> ⚠️ **Actualizado 2026-06-12 (revisión integral):**
> - Los filtros de **Product type** y **Source class** no tienen UI (los facets
>   `productTypes`/`sourceClasses` se eliminaron de `buildFacets`); los params
>   siguen funcionando por URL.
> - **País** muestra la lista completa (~14, antes top 10 — dejaba países sin
>   checkbox). **Editorial** top 12 e **Idioma** top 8, recortados en el SERVER
>   antes de serializar al client component (los ~400 publishers completos
>   viajaban en el payload RSC).
> - "Limpiar todo" **conserva `sort`** (el orden no es un filtro) y cancela el
>   debounce de búsqueda pendiente (antes un commit en vuelo re-aplicaba la
>   búsqueda recién borrada).
> - Los mutadores de URL leen `window.location.search` (URL viva), no el
>   snapshot del hook — dos interacciones en la misma ventana de debounce ya no
>   se pisan.
> - El SearchBar del header, en páginas de detalle, navega a `/?q=…` (la página
>   de detalle es estática e ignora searchParams; antes la búsqueda no hacía nada).
> - `parseFilterParams` sanea params hostiles (`?q=a&q=b`, `?page=abc`, sort
>   desconocido) — ver FRD-001 FR-6.
> - Drawer móvil: Escape cierra, scroll del body bloqueado, foco al abrir.

**Active filter summary:** When any filter is active, a "Limpiar filtros" link
appears below the title. Each active filter shows as a dismissible tag.

**Facet counts** in the sidebar show the count from the **unfiltered** corpus
(not dynamic — stable counts regardless of other active filters).

### FR-4: Sort bar

Located above the grid:

```
10.064 tomos · 5628 ediciones · 3225 obras · pág. 1/94    [Sort ▾]    [Filtros]
```

All three counters reflect the **currently filtered** corpus (not the total corpus), so
applying a filter updates all three numbers simultaneously.

- **tomos** — `filtered.length` (distinct item clusters before `groupByEdition`)
- **ediciones** — `editions.length` (distinct edition groups after `groupByEdition`)
- **obras** — count of distinct `series_key` values across filtered clusters

Number style: semibold (`font-weight: 600`), `color-text-primary`. Label style: 12px,
`color-text-tertiary`. Separated by `·`. Pagination `pág. N/M` on the same line.

Sort options (select dropdown):
- Más recientes (date desc) — **default** (era "score desc" hasta 2026-06-01)
- Más antiguos (date asc)
- Título A→Z
- Título Z→A

> **Removido (2026-06-01):** las opciones "Mejor/Menor puntuación (score)" se
> eliminaron. El canónico de cada cluster ahora se elige por completitud
> (ISBN > imagen) en vez de por score.
>
> **Actualizado 2026-06-12:** el orden por fecha usa `sortableDate()` — los
> `DD/MM/YYYY` legacy se normalizan a ISO antes de comparar (un item de 2023
> ordenaba como el más reciente del catálogo).

### FR-5: Pagination

- 60 items per page
- URL param: `?page=N`
- Visible page window: current ± 2, always first/last, ellipsis when gap > 1
- "Showing X–Y of Z ediciones" counter
- **`router.push()`** (no `replace`, 2026-06-12): cada página es entrada de
  historial — "atrás" desde la pág. 5 vuelve a la 4, no sale del sitio. Los
  filtros y el tipeo debounced siguen usando `replace` (correcto ahí).
- `?page` fuera de rango se clampa; no numérico cae a 1 (antes: grid vacío
  con "pág. NaN").

### FR-6: Filter state in URL

All filter state is encoded in URL search params:

```
/?q=berserk&country=JP&country=FR&signal_types=box_set&rarity=super_rare&sort=date_desc&page=2
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

---

## Addendum 2026-07-08 — paquete H2-webnext-ui (auditoría Fable)

- **`useCatalogParams()` (`lib/useCatalogParams.ts`, auditoría #11)**: fuente
  única de mutación de URL — antes reimplementada en SidebarFilters/
  SearchBar/SortBar/Pagination con matices propios (algunos leían
  `window.location.search`, otros el snapshot del hook — bug latente si dos
  mutadores disparaban en la misma ventana). `set`/`toggle`/`clearAll` SIEMPRE
  leen la URL viva y borran `page`. Envuelve la navegación en `useTransition`
  — `isPending` da feedback (opacity/spinner) mientras el Server Component
  re-renderiza (auditoría #7).
- **Un solo buscador visible en desktop (auditoría #16)**: el input del
  sidebar se eliminó — reutiliza el `<SearchBar/>` del header (mismo
  componente, mismo debounce 600ms) SOLO dentro del drawer móvil.
- **`product_type` como facet (auditoría #21)**: antes `FilterParams`/
  `filterClusters` ya lo soportaban pero sin UI — ahora hay chips en el
  sidebar (`lib/facets.ts` → `productTypeFacet()`, labels de
  `PRODUCT_TYPE_LABELS`). `hasActiveFilters`/`clearAll` ahora también
  consideran `product_type`/`source_class`.
- **Drawer móvil vía `<dialog>` (auditoría #13)**: `showModal()` da focus
  trap + Escape + backdrop-click gratis, sin dependencia — antes el foco se
  escapaba con Tab pese a `aria-modal="true"`.
- **`hasActiveFilters` completo (auditoría #21)**.
