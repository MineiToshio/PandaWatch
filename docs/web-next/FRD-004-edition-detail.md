# FRD-004: Edition Detail Page

**Version:** 1.0  
**Status:** Draft  
**Author:** Architecture session 2026-05-27  
**Related:** [BP-002](blueprints/BP-002-url-routing.md), [WO-005](work-orders/WO-005-edition.md)

---

## Overview

The edition detail page (`/edition/[editionKey]`) shows all volumes (items) that
belong to a specific edition — same series + publisher + edition type. It is the
"middle level" between the catalog grid and the individual item detail.

Example: `/edition/berserk-darkhorse-deluxe` shows Berserk Deluxe Edition Vol. 1
through Vol. 15 (or however many are in the corpus).

---

## Problem Statement

In the Alpine.js app, navigating into an edition uses hash routing (`#/edition/key`)
and renders as an in-page state change. There is no shareable URL, no server
rendering, and no `<title>` change. The edition view is just a filtered subset of
the same `items` array.

The Next.js edition page is a proper route with a real URL, server-rendered content,
and correct `<title>` / `<meta>` tags for social sharing.

---

## User Stories

- As a **collector**, I want to see all volumes of "Berserk Deluxe Edition" in one
  place so I can identify which ones I'm missing.
- As a **user**, I want to share the URL of a specific edition with another collector.
- As a **user**, I want to go back to the catalog with my filters preserved.

---

## Functional Requirements

### FR-1: Route and static generation

Route: `/edition/[editionKey]`

`generateStaticParams()` returns all distinct `edition_key` values from `items.jsonl`.
The page is statically generated at build time for each edition key.

If an `editionKey` not found in the corpus is requested, the page returns 404
via `notFound()`.

### FR-2: Page header

Displays edition-level metadata extracted from the cluster set:

| Field | Source |
|---|---|
| Series title | `canonical.series_display` |
| Edition name | `canonical.edition_display` |
| Publisher | `canonical.publisher` |
| Country | `canonical.country` (with flag emoji) |
| Total volumes | Count of distinct volumes in this edition |
| Signal type chips | Union of all signal_types across the edition |

**Removed:** "Score range" was removed 2026-05-30. Score is not user-facing.

### FR-3: Volume grid

Displays `ItemCard` components for each volume/item in the edition, sorted by
volume number ascending. Items without a volume number appear last, sorted by
`detected_at` descending.

**ItemCard** (edition-context variant) shows:
- Cover image
- Volume number badge (top-left corner of cover)
- Title (volume-level title, not series title)
- Price — only when `parseFloat(price) > 0`; hidden when zero or absent
- Release date
- Signal type chips (up to 2, overflow as "+N")

**Removed:** Score badge was removed from ItemCard 2026-05-30.

Clicking an ItemCard navigates to `/item/[slug]`.

### FR-4: Back navigation

A `← Catálogo` link at the top-left of the page. It navigates to `/` preserving
the referring URL's search params if the user arrived from the catalog
(implemented via `<Link href={referrer || "/"}>` where referrer is passed as a
query param `?from=...` by the edition card click handler).

### FR-5: Multi-source note

If any item in the edition has more than one source, a subtle note appears:
"Esta edición aparece en N fuentes." (no detailed source UI at this level —
that's for the item detail page).

### FR-6: SEO metadata

```tsx
export async function generateMetadata({ params }) {
  const clusters = clusterByEditionKey(params.editionKey)
  const canonical = clusters[0]?.canonical
  return {
    title: `${canonical.edition_display} — PandaWatch`,
    description: `${clusters.length} tomos de ${canonical.series_display}
                  (${canonical.publisher}, ${canonical.country})`,
    openGraph: {
      images: [canonical.image_url || canonical.image_local],
    }
  }
}
```

---

## Non-Functional Requirements

- **Static generation:** All edition pages are pre-built at `next build`. No
  per-request server work in production.
- **Performance:** Each edition page is pure HTML — no client JS unless the user
  interacts with a Client Component.

---

## Out of Scope

- Editing or managing edition metadata.
- "Related editions" suggestions.
- "Missing volumes" comparison against a user collection (future feature).

---

## Acceptance Criteria

- [x] `/edition/berserk-darkhorse-deluxe` loads and shows all Berserk Deluxe volumes
- [x] Volumes are sorted by volume number ascending
- [x] Items without volume numbers appear at the end
- [x] Page title is `"Berserk Deluxe Edition — PandaWatch"` (example)
- [x] `← Catálogo` navigates back to `/`
- [x] Requesting a non-existent edition key returns 404
- [x] `generateStaticParams()` generates a route for every edition_key in the corpus

---

## Dependencies

- FRD-001 (data layer) — `loadEditionClusters()`, `allEditionKeys()`
- FRD-002 (design system) — Chip, Badge, Typography, Button
- FRD-006 (slug generation) — needed for ItemCard click navigation
