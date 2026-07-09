# FRD-005: Item Detail Page

**Version:** 1.2  
**Status:** Implemented (updated 2026-05-30)  
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
- As a **buyer**, I want to see all sources where I can purchase the item.
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
                        Título OFICIAL (no se renombra/traduce)
                        Título original: … (si difiere)
                        🎁 Bonus de tienda: … (si store_bonus)
                        Publisher · Country · Language

                        [Signal chips]

                        [Rarity badge]

                        Fecha: DD/MM/YYYY
                        ISBN: XXXXXXXXXXXXXXXXX
                        Autor: XXXXXX
```

On mobile: carousel on top, metadata below (stacked layout).
On desktop: carousel on left (40%), metadata on right (60%).

**Título + bonus de tienda (política de títulos 2026-06-12):** el `title` es el
nombre OFICIAL del producto (no se traduce ni renombra; ver
[title-policy.md](../../reference/title-policy.md)). `title_original` se muestra
debajo si difiere. **`store_bonus`** (perk de compra de un retailer JP, 店舗特典,
separado del título por gotcha #93) se muestra como línea ámbar "🎁 Bonus de
tienda: …" cuando está presente — NO va en el grid, solo acá en el detalle.

**Rarity badge (glassy mode):** rendered as an inline pill below the signal chips using
the glassy display mode (dark background `rgba(20,17,14,0.82)` + `backdrop-filter: blur(6px)`,
border `1px solid rgba(255,255,255,0.12)`, bright-on-dark foreground). Includes SVG icon
matching the tier (circle / star / sparkle / gem). Hidden when `rarity` is absent.
See FRD-002 FR-3 for the full glassy-mode spec.

**Score badge removed:** `ScoreBadge` is no longer rendered in `ItemHero` (removed 2026-05-30).

### FR-3: Image carousel (Client Component)

Located in `components/item/ImageCarousel.tsx`. Uses `"use client"`.

The carousel shows the **cluster-level union** of `images[]` (built in
`ItemHero.tsx` from `cluster.items`, not just `canonical.images`), so it matches
the Alpine dashboard's detail carousel. Dedup by URL stem (no scheme/query); the
canonical cover (`canonical.image_url`, the one the card shows) is **always first**
so `carousel[0] == card cover`. This invariant must match the other two merge
sites — `web/index.html` `dedupByUrl` and `scripts/build_web.py`
`_merged_canonical` (2026-06-02).
- position 0 — main cover (synced with the card)
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

### FR-5: Description

Below the metadata block in `ItemHero`, display the item description in Spanish.

**Priority / fallback rule (same pattern in both web apps):**
```
description_es || description
```

- `description_es` is the Spanish translation generated by `translate_descriptions.py`.
- If `description_es` is absent or empty (item's description was already in Spanish),
  fall back to `description`.
- The block is hidden entirely when both fields are empty/absent.

**Implementation:** `components/item/ItemHero.tsx`, condition:
```tsx
{(canonical.description_es || canonical.description) && (
  <p>…{canonical.description_es || canonical.description}…</p>
)}
```

### FR-6: Extras section

If `extras[]` is non-empty, show a section "Incluye / Extras de primera edición":

Each entry in `extras[]`:
- Description in Spanish: `extra.description_es || extra.description`
  (same fallback rule as FR-5 — implemented in `ExtrasSection.tsx`)
- Release date if different from main item

### FR-7: Metadata table

Full metadata in a clean definition list:

| Label | Field |
|---|---|
| ISBN | `isbn` (formatted as ISBN-13 with dashes if possible) |
| Lanzamiento | `release_date` (formatted DD/MM/YYYY) |
| Autor | `author` |
| Editorial | `publisher` |
| País | `country` + flag emoji |
| Idioma | `language` |
| Tipo | `product_type` (translated to Spanish) |
| Rareza | `rarity` translated: common → "Accessible", rare → "Rare", super_rare → "Super Rare", ultra_rare → "Ultra Rare" |
| Detectado | `detected_at` (formatted) |
| Estandarizado | `standardized_at` (formatted, or "Pendiente" if null) |

**Removed:** "Puntuación" row (`score` + `ScoreBadge`) was removed 2026-05-30. Score is an
internal signal-detection metric, not a user-facing quality indicator.

### FR-8: Sources table

Las fuentes viven en **`canonical.sources[]`** (modelo 1-fila-por-producto,
2026-06-02): cada fila de items.jsonl ya trae todas las fuentes donde se
encontró el producto. `SourcesList` recibe `sources: SourceEntry[]` (NO
`items: Item[]` — antes derivaba de `cluster.items`, que ahora es 1 sola fila,
y mostraba "Fuentes (1)" perdiendo las hermanas). Fallback: si la fila no trae
`sources[]` (datos legacy), se deriva de `cluster.items`. Se muestra cuando
`sources.length > 1`.

| Column | Campo (de `SourceEntry`) |
|---|---|
| Fuente | `name` (+ link externo a `url`) |
| Fecha | `release_date` |
| Stock | `stock_type` |

> Nota relacionada: `lib/data.ts buildCluster` también une `country`/
> `publisher`/`language` desde `canonical.sources[]` (no solo de las filas),
> para que un producto multi-fuente no pierda los países/editoriales de las
> fuentes hermanas en facetas y badges.

### FR-9: Navigation

**Back navigation:**
- Item con `edition_key` → fallback `← {editionDisplay}` (a `/edition/[editionKey]`)
- Item standalone → fallback `← Catálogo` (a `/`)

> ⚠️ **Actualizado 2026-06-12:** ya NO se implementa con `?from=` (eliminado —
> ver FRD-004 FR-4 y FRD-008 §Implementación). El fallback se deriva
> estáticamente del dato (`canonical.edition_key`); con navegación interna
> previa, `BackLink` usa `history.back()` y restaura el estado exacto.

**Sibling navigation (optional, nice-to-have):**
Within an edition, Previous / Next volume arrows at the bottom of the page.

### FR-10: SEO metadata

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
- [ ] Description shows `description_es` when available, falls back to `description`
- [ ] Description block hidden when both `description_es` and `description` are empty
- [ ] Extras section appears when `extras[]` is non-empty; extras show `description_es || description`
- [ ] Sources table shows all cluster sources when count > 1
- [ ] `← Catálogo` or `← {editionDisplay}` navigates correctly
- [ ] Requesting a non-existent slug returns 404
- [ ] `generateStaticParams()` generates a route for every slug in the corpus

---

## Dependencies

- FRD-001 (data layer) — `clusterBySlug()`, `allSlugs()`
- FRD-002 (design system) — all core components
- FRD-006 (slug generation) — `slug` field must exist in items.jsonl

---

## Addendum 2026-07-08 — paquete H2-webnext-ui (auditoría Fable)

- **Carrusel sin interactivos anidados (auditoría #9)**: antes las flechas
  prev/next eran `<button>` DENTRO de un `<div role="button">` — inválido en
  ARIA. Ahora: contenedor neutro `role="group"`, un único
  `<button aria-label="Ampliar imagen">` que envuelve SOLO la imagen, flechas
  como hermanas absolutas.
- **Dots táctiles 24×24 (auditoría #22)**: el botón mide 24×24 (WCAG 2.5.8),
  el punto visual sigue siendo 8px, centrado.
- **Lightbox vía `<dialog>` (auditoría #13)**: `showModal()` reemplaza el
  manejo manual de foco/Escape/scroll-lock — focus trap gratis.
- **`referrerPolicy="no-referrer"` en `<img>` remotos** (auditoría #15) —
  muchas tiendas bloquean hotlinks por Referer.
- **MetaTable sin jerga de pipeline (auditoría #18)**: se quitaron
  "Detectado"/"Estandarizado: Pendiente" (esta última rama era inalcanzable);
  "Detectado" se reformuló como "En el catálogo desde".
