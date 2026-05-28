# FRD-005: Item Detail Page

**Version:** 1.0  
**Status:** Draft  
**Author:** Architecture session 2026-05-27  
**Related:** [BP-002](blueprints/BP-002-url-routing.md), [BP-004](blueprints/BP-004-component-hierarchy.md), [WO-006](work-orders/WO-006-item-detail.md)

---

## Overview

The item detail page (`/item/[slug]`) shows the full information for a single
catalog item (which may represent multiple sources via cluster merging). This is
the "deepest" level — a specific volume, box set, artbook, or standalone item.

Example: `/item/berserk-darkhorse-deluxe-42` shows Berserk Deluxe Edition Vol. 42
with all available metadata, image carousel, and list of sources.

---

## Problem Statement

In the Alpine.js app, the "volume" detail view is a modal that overlays the
catalog. It has no URL, cannot be bookmarked, cannot be shared, and is not
indexable. The image carousel, extras, and source table are implemented in Alpine.js
reactive state — all client-side.

The Next.js item detail page is a real URL with server-rendered content, a proper
`<title>`, and a Client Component only for the interactive image carousel.

---

## User Stories

- As a **collector**, I want to see all available images for an item (cover +
  gallery + extras) in a carousel.
- As a **user**, I want to know exactly what extras come with a special edition
  (bookmarks, postcards, shikishi, etc.).
- As a **buyer**, I want to see all sources where I can purchase the item, with
  their respective prices.
- As a **user**, I want to share the exact URL of a specific volume with a friend.

---

## Functional Requirements

### FR-1: Route and static generation

Route: `/item/[slug]`

`generateStaticParams()` returns all distinct `slug` values from `items.jsonl`.
The page is statically generated at build time for each slug.

If a slug is not found, the page returns 404 via `notFound()`.

### FR-2: Page header (ItemHero)

```
[  IMAGE CAROUSEL  ]   [  METADATA  ]

                        Series Display
                        Edition Display — Vol. N
                        Publisher · Country · Language
                        
                        [Score badge]  [Signal chips]
                        
                        Precio: €XX.XX
                        Fecha: DD/MM/YYYY
                        ISBN: XXXXXXXXXXXXXXXXX
                        Autor: XXXXXX
```

On mobile: carousel on top, metadata below (stacked layout).
On desktop: carousel on left (40%), metadata on right (60%).

### FR-3: Image carousel (Client Component)

Located in `components/item/ImageCarousel.tsx`. Uses `"use client"`.

The carousel shows the `images[]` array from the canonical item:
- `kind=cover` — main cover (always first)
- `kind=gallery` — additional product photos
- `kind=extra` — photos of included extras (postcards, shikishi, etc.)

**Controls:**
- Previous / Next arrow buttons
- Dot indicators (max 8 dots; more images = no dots, just arrows)
- Kind label badge on the image: "Portada" / "Galería" / "Extra"
- Description below the image (from `images[i].description`) — e.g., "Postal edición limitada"

**Fallback behavior:**
1. Try `images[i].local` → `/images/{filename}`
2. Try `images[i].url` (remote)
3. Show 📚 placeholder

**Keyboard support:** Left/Right arrow keys when the carousel is focused.

**Swipe support:** Touch swipe left/right on mobile.

### FR-4: Signal types section

Row of `SignalChip` components showing all signal types for this item.
Each chip has an icon and a descriptive label:

| Signal | Icon | Label |
|---|---|---|
| `limited` | 🏷️ | Edición Limitada |
| `special_edition` | ⭐ | Edición Especial |
| `collector` | 🏆 | Edición Coleccionista |
| `box_set` | 📦 | Cofre / Box Set |
| `variant_cover` | 🎨 | Portada Alternativa |
| `artbook` | 🖼️ | Artbook |
| `deluxe` | 💎 | Edición Deluxe |
| `hardcover` | 📚 | Tapa Dura / Cartoné |
| `kanzenban` | 🗾 | Kanzenban |
| `lore_edition` | ✨ | Edición Especial Named |
| `omnibus` | 📖 | Ómnibus |
| `bonus` | 🎁 | Con Extra de Regalo |
| `retailer_exclusive` | 🏪 | Exclusivo Tienda |

### FR-5: Extras section

If `extras[]` is non-empty, show a section "Incluye / Extras de primera edición":

Each entry in `extras[]`:
- Description (e.g., "Postal con ilustración exclusiva")
- Release date if different from main item

### FR-6: Metadata table

Full metadata in a clean definition list:

| Label | Field |
|---|---|
| ISBN | `isbn` (formatted as ISBN-13 with dashes if possible) |
| Precio | `price` (from best source) |
| Fecha de lanzamiento | `release_date` (formatted DD/MM/YYYY) |
| Autor | `author` |
| Editorial | `publisher` |
| País | `country` + flag emoji |
| Idioma | `language` |
| Tipo | `product_type` (translated to Spanish) |
| Clase de fuente | `source_class` |
| Puntuación | `score` with ScoreBadge |
| Detectado | `detected_at` (formatted) |
| Estandarizado | `standardized_at` (formatted, or "Pendiente" if null) |

### FR-7: Sources table

If the cluster has more than one source, show a "Fuentes" section:

| Column | Field |
|---|---|
| Fuente | `source` |
| URL | Clickable link (external icon) |
| Precio | `price` per source |
| Fecha | `release_date` per source |
| Stock | `stock_type` |

### FR-8: Navigation

**Back navigation:**
- If arrived from `/edition/[editionKey]`: show `← {editionDisplay}` link
- If arrived from `/`: show `← Catálogo` link
- Default: `← Catálogo`

Implemented via query param `?from=edition:{editionKey}` set by ItemCard's link.

**Sibling navigation (optional, nice-to-have):**
Within an edition, Previous / Next volume arrows at the bottom of the page.

### FR-9: SEO metadata

```tsx
export async function generateMetadata({ params }) {
  const cluster = clusterBySlug(params.slug)
  return {
    title: `${cluster.canonical.title} — PandaWatch`,
    description: buildDescription(cluster.canonical),
    openGraph: {
      images: [cluster.canonical.image_url],
      type: 'book',
    }
  }
}
```

---

## Non-Functional Requirements

- **Static generation:** All item pages pre-built at `next build`.
- **Hydration minimal:** Only `ImageCarousel` is a Client Component. All other
  content is static HTML.
- **Accessibility:** Carousel has `aria-label`, arrow buttons have `aria-label`,
  current image has `aria-current`. Keyboard navigation works.

---

## Out of Scope

- Edit / feedback (👎 removal) — stays in `serve.py` / Alpine.js `web/index.html`.
- "Add to wishlist" or collection tracking (future feature for PandaTrack integration).
- Comments or user reviews.

---

## Acceptance Criteria

- [ ] `/item/berserk-darkhorse-deluxe-42` loads with correct data
- [ ] Image carousel shows all images in `images[]` array
- [ ] Carousel arrows and dots work; keyboard left/right works
- [ ] Image kind badge shows "Portada" / "Galería" / "Extra" correctly
- [ ] Signal type chips show correct icons and labels
- [ ] Extras section appears when `extras[]` is non-empty
- [ ] Sources table shows all cluster sources when count > 1
- [ ] `← Catálogo` or `← {editionDisplay}` navigates correctly
- [ ] Requesting a non-existent slug returns 404
- [ ] `generateStaticParams()` generates a route for every slug in the corpus

---

## Dependencies

- FRD-001 (data layer) — `clusterBySlug()`, `allSlugs()`
- FRD-002 (design system) — all core components
- FRD-006 (slug generation) — `slug` field must exist in items.jsonl
