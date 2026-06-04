# FRD-007: Series Highlights & Series Page

**Version:** 1.0
**Status:** Draft
**Author:** Design session 2026-06-03
**Related:** [BP-002](blueprints/BP-002-url-routing.md), [FRD-001](FRD-001-data-layer.md), [FRD-003](FRD-003-catalog.md), [WO-008](work-orders/WO-008-series-page.md)

---

## Overview

Two complementary features that introduce the **series (obra)** as a first-class
navigable level above editions:

1. **Series highlights strip** — a "Obras destacadas" section at the top of the
   home page (`/`) showing a curated top of works as cards.
2. **Series page** — a new route `/series/[seriesKey]` that shows **all editions
   and items of a single work** in one place.

Clicking a highlight card opens its series page; from there the user drills down
into editions and items via the existing hierarchy.

This adds the missing top level to the navigation hierarchy:

```
SERIES (obra)        ← NEW (/series/[seriesKey])
   └─ EDITION         (/edition/[editionKey])
        └─ ITEM       (/item/[slug])
```

---

## Problem Statement

Today the home page drops the visitor straight into a flat grid of ~5.6k edition
cards sorted by date. There is:

- **No entry point by work.** A collector who wants "everything for One Piece"
  has to type it in the search box and scroll; there is no way to *discover* which
  works the catalog is richest in.
- **No series-level view.** The catalog groups by `edition_key`, so the 84
  distinct One Piece editions appear as 84 separate cards scattered across pages —
  never as "One Piece, the work, with all its editions in one screen."
- **No showcase of breadth.** PandaWatch's whole identity is *special editions*.
  The works with the most distinct special editions (One Piece: 84, Attack on
  Titan: 34, Demon Slayer: 29, Berserk: 26, Witch Hat Atelier: 24…) are exactly
  what makes the catalog interesting, but nothing surfaces them.

The series highlights + series page solve all three: a discovery surface on the
home page, and a dedicated, indexable, shareable view per work.

---

## Concepts & Data Model

The corpus already carries the fields needed — **no schema change**.

| Level | Group-by field | web-next type | Existing route |
|---|---|---|---|
| Series (obra) | `series_key` | `Series` *(new)* | `/series/[seriesKey]` *(new)* |
| Edition | `edition_key` | `Cluster` (after `groupByEdition`) | `/edition/[editionKey]` |
| Product | `cluster_key` | `Cluster` | `/item/[slug]` |

A **work / obra / serie** = all standardized items sharing a `series_key`. The
`series_key` is already a kebab-case slug (`one-piece`, `witch-hat-atelier`), so
it doubles as the URL segment — **no new slug generation needed** (unlike items,
FRD-006).

Corpus snapshot (2026-06-03, standardized rows only):
- **3 227** distinct `series_key`.
- **815** series with ≥ 2 editions.
- Image coverage on the top works is ~100%, so highlight cards always render a cover.

---

## User Stories

- As a **collector**, I land on the home page and immediately see the works the
  catalog tracks most heavily, so I can dive into one I care about.
- As a **One Piece collector**, I click the One Piece card and see *all* its
  editions (Color Walk artbooks, box sets, anniversary, regional variants…) in one
  screen, then drill into any edition.
- As a **visitor sharing a link**, I send `…/series/berserk` to a friend and they
  see the same dedicated Berserk page (server-rendered, indexable).
- As a **returning user browsing filtered results**, I am *not* shown the
  highlights strip — it only appears on the unfiltered landing view, so it never
  gets in the way while I'm searching.

---

## Functional Requirements

### FR-1: The `Series` aggregate (data layer)

A new `Series` type and loader functions in `lib/data.ts`. A `Series` aggregates
all clusters that share `canonical.series_key`:

| Field | Source |
|---|---|
| `seriesKey` | `canonical.series_key` |
| `seriesDisplay` | `canonical.series_display` (fallback: prettified key) |
| `cover` | `{ imageLocal, imageUrl }` of the **most complete** item in the series that has an image |
| `editionCount` | count of distinct `edition_key` across the series |
| `itemCount` | count of distinct `cluster_key` (products) in the series |
| `countries` | union of cluster countries |
| `publishers` | union of cluster publishers |
| `signalTypes` | union of cluster signal types |
| `topRarity` | highest rarity tier present (`ultra_rare > super_rare > rare > common`), optional |

Clusters whose `canonical.series_key` is empty are **excluded** (they have no work
to belong to).

Loader functions:

- `loadSeries(): Series[]` — build and rank all series (see FR-2 for the order).
- `topSeries(limit = 12): Series[]` — `loadSeries()` filtered to those with a
  cover, sliced to `limit`.
- `seriesByKey(seriesKey): Series | null` — single series for the series page header.
- `loadSeriesEditions(seriesKey): Cluster[]` — the clusters of that series passed
  through `groupByEdition()` (so the series page reuses the catalog's edition
  grouping), sorted by edition richness then title.
- `allSeriesKeys(): string[]` — distinct keys for `generateStaticParams()`.

Reuse the existing private `completeness()` helper (ISBN > image > price) to pick
the canonical cover, mirroring how clusters pick their canonical.

### FR-2: Ranking criterion ("top de obras")

**Decision:** rank by **distinct edition count, descending**, tie-broken by
**distinct product (cluster) count, descending**, then **series display A→Z**.

```
sort key = (editionCount, itemCount, -collator(seriesDisplay))  // all desc except name
```

**Rationale.** PandaWatch is a *special-editions* tracker. The number of distinct
editions a work has is the most faithful measure of "how much is there to collect
here" — it is the headline metric. Item count is the depth tiebreaker so that, e.g.,
two works with 17 editions order by how many products back them. Validated against
the corpus, this surfaces a clean, recognizable marquee:

> One Piece (84) · Attack on Titan (34) · Demon Slayer (29) · Berserk (26) ·
> Witch Hat Atelier (24) · Blue Lock (22) · Naruto (22) · Fullmetal Alchemist (21) ·
> My Hero Academia (20) · Death Note (20) · The Promised Neverland (20) ·
> Jujutsu Kaisen (19) …

The ranking lives in a single comparator in `loadSeries()` and is trivially
swappable (e.g. to weight item count higher, or to add a recency component) — keep
it isolated so retuning is a one-line change.

### FR-3: Series highlights strip (home page)

A `SeriesHighlights` Server Component rendered **above** the catalog controls on
`/`.

- **Header:** title "Obras destacadas" + one-line subtitle
  ("Las series con más ediciones especiales en el catálogo.").
- **Layout:** a single-row **horizontal scroll strip** (snap scrolling), visually
  distinct from the catalog grid below it. Cards ~150–160px wide; the strip scrolls
  horizontally on every viewport, showing ~8 at once on desktop. (Horizontal strip
  chosen over a grid so the section reads as a curated "carousel", not a second
  catalog.)
- **Count:** `topSeries(12)` — top 12 works.
- **Conditional visibility:** render the strip **only on the default landing view**
  — i.e. when there is no active search (`q`), no active filters, and `page === 1`.
  While the user is filtering or paginating, the strip is hidden so it never
  competes with their results.

### FR-4: Series card (`SeriesCard`)

A compact work card used in the highlights strip:

- **Cover** — `cover.imageLocal` via `/images/{file}` → `cover.imageUrl` remote
  fallback → 📚 placeholder, using the shared `CoverImage` component, `aspect-ratio: 2/3`.
- **Series name** — `seriesDisplay`, up to 2 lines (clamp).
- **Stats line** — `"{editionCount} ediciones · {itemCount} tomos"`
  (singular/plural aware: "1 edición", "1 tomo").
- **Country flags** — up to 3, bottom-left over the cover (reuse `CountryFlag`),
  matching `EditionCard`.
- **Optional rarity accent** — if `topRarity` is `ultra_rare`/`super_rare`, a small
  badge may be shown (reuse `EditionCard`'s `RarityBadge` styling). Optional for v1.
- **Link** — entire card links to `/series/{seriesKey}`.
- **Hover** — slight lift, consistent with `EditionCard`.

Uniform height like `EditionCard`: fixed-height info block so all cards align.

### FR-5: Series page (`/series/[seriesKey]`)

A new Server Component route, statically generated.

- **Back link** — `BackLink` to `from` query param (default `/`).
- **Header** (`SeriesHeader`, modeled on `EditionHeader`):
  - Cover thumbnail (representative item).
  - Series name (`seriesDisplay`) as `<h1>`.
  - Stats: `"{editionCount} ediciones · {itemCount} tomos"` + country flags.
  - Signal-type chips — union across the series (reuse `SignalChip`).
- **Editions grid** — `loadSeriesEditions(seriesKey)` rendered through the existing
  `CatalogGrid` (so cards, stack effect, navigation are identical to the catalog).
  - Each edition card links to `/edition/[editionKey]` (multi-volume) or
    `/item/[slug]` (single-volume / standalone), exactly as on the catalog, via the
    existing `EditionCard` logic.
  - Pass `from = /series/{seriesKey}` so that back-navigation from an edition/item
    returns to **this** series page (reuses the existing `?from=` mechanism).
- **Not found:** if `seriesKey` has no standardized items, return 404 (`notFound()`).
- **Metadata:** `generateMetadata()` sets
  `title = "{seriesDisplay} — PandaWatch"`, a description with the edition/item
  counts, and `openGraph.images` = the cover.
- **Static generation:** `generateStaticParams()` over `allSeriesKeys()`.

### FR-6: Navigation flow

```
HOME (/)
  │  click SeriesCard (highlights strip)
  ▼
SERIES (/series/[seriesKey])
  │  click EditionCard (multi-volume)        │  click EditionCard (single / standalone)
  ▼                                          ▼
EDITION (/edition/[editionKey])              ITEM (/item/[slug])
  │  ← back (?from=/series/[seriesKey])         │  ← back
  ▼                                          ▼
SERIES (/series/[seriesKey])  ←──────────────┘
  │  ← back (?from=/)
  ▼
HOME (/)
```

The series page also functions as a landing target for any future "search this
work" affordance — e.g. a link from the item/edition header's series name (out of
scope for this FRD, but the route makes it trivial later).

---

## Non-Functional Requirements

- **SEO:** series pages are server-rendered + statically generated. Each work gets a
  crawlable, indexable URL.
- **Performance:** `loadSeries()` reuses the already-cached `loadClusters()` output;
  no extra file reads. The highlights strip is ~12 cards of static HTML.
- **Consistency:** the series page reuses `CatalogGrid` / `EditionCard` / `CoverImage`
  / `SignalChip` / `CountryFlag` / `BackLink` so it inherits the design system with
  no new visual primitives beyond `SeriesCard` and `SeriesHeader`.
- **No schema change, no Python change.** Pure web-next addition.

---

## Out of Scope

- A full `/series` index page listing **all** works (the highlights strip is curated
  top-N only). Reserved as a future route.
- Sorting/filtering controls *within* the series page (it shows all editions of one
  work; the global catalog already has filters).
- Cross-publisher merging beyond `series_key` (the corpus already canonicalizes
  multilingual names into one `series_key` via `series_aliases.yml`).
- Linking the series name in the edition/item headers to the series page (nice
  follow-up, not required here).

---

## Acceptance Criteria

- [ ] `loadSeries()` returns one `Series` per distinct non-empty `series_key`, ranked
      by (editionCount desc, itemCount desc, name asc).
- [ ] The home page shows an "Obras destacadas" strip of 12 work cards on the
      default view, and hides it when any filter/search is active or `page > 1`.
- [ ] Each `SeriesCard` shows cover, series name, `"N ediciones · M tomos"`, and
      country flags, and links to `/series/{seriesKey}`.
- [ ] `/series/one-piece` renders the One Piece header + a grid of all its editions
      (84), each edition card navigating to its edition/item page.
- [ ] Back-navigation from an edition opened via the series page returns to the
      series page, not the catalog.
- [ ] `/series/<nonexistent>` returns 404.
- [ ] `generateStaticParams()` produces a route per `series_key`; `npm run build`
      succeeds and type-checks cleanly.
- [ ] No regression: catalog, edition, and item pages behave exactly as before.

---

## Dependencies

- FRD-001 (data layer) — `loadClusters()`, `groupByEdition()`, `completeness()`.
- FRD-003 (catalog) — `CatalogGrid`, `EditionCard`.
- FRD-002 (design system) — `CoverImage`, `SignalChip`, `CountryFlag`, `BackLink`.
- BP-002 (routing) — `/series/[seriesKey]` promoted from "future" to active.
