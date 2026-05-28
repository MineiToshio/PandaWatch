# PandaWatch App — Next.js Public Frontend

> **Scope:** This folder documents the Next.js 16 + Tailwind v4 application at `web-next/`,
> the **public-facing** frontend for PandaWatch. The scraping pipeline, JSONL data store,
> and Python scripts are unchanged.
>
> **Methodology:** 80/90.AI — simplified variant.
> Each feature area has an FRD → Blueprint → one or more Work Orders.

---

## What is "PandaWatch App"?

**PandaWatch** is the whole project (scraper + data + dashboards).
**PandaWatch App** (`web-next/`) is the public Next.js frontend. It **complements**, not
replaces, `web/index.html` (the personal curation dashboard):

| | `web/index.html` | `web-next/` |
|---|---|---|
| Audience | Owner only | Public |
| Purpose | Explore, curate, give feedback (👎) | Discover, browse, navigate |
| Feedback (👎) | ✅ implemented | ❌ out of scope permanently |
| Deploy | `localhost:8000` | Vercel / Cloudflare Pages |

The app:
- Reads `data/items.jsonl` server-side (Server Components, no API routes)
- Serves the catalog, edition detail, and item detail views
- Ports the full PandaTrack design system (OKLCH tokens, CVA, dark mode)
- Will be the base for a future multi-user deployment (SQLite → Postgres migration path preserved)

---

## Document Index

### FRDs — Functional Requirements

| ID | Title | Status |
|---|---|---|
| [FRD-001](FRD-001-data-layer.md) | Data Layer | Draft |
| [FRD-002](FRD-002-design-system.md) | Design System | Draft |
| [FRD-003](FRD-003-catalog.md) | Catalog Page | Draft |
| [FRD-004](FRD-004-edition-detail.md) | Edition Detail Page | Draft |
| [FRD-005](FRD-005-item-detail.md) | Item Detail Page | Draft |
| [FRD-006](FRD-006-slug-generation.md) | Slug Generation | Draft |

### Blueprints — Technical Design

| ID | Title |
|---|---|
| [BP-001](blueprints/BP-001-architecture.md) | Architecture Overview |
| [BP-002](blueprints/BP-002-url-routing.md) | URL & Routing Schema |
| [BP-003](blueprints/BP-003-data-flow.md) | Data Flow & Server Rendering |
| [BP-004](blueprints/BP-004-component-hierarchy.md) | Component Hierarchy |

### Work Orders — Implementation Tasks

| ID | Title | Phase | Depends on |
|---|---|---|---|
| [WO-001](work-orders/WO-001-project-scaffold.md) | Project Scaffold | 0 | — |
| [WO-002](work-orders/WO-002-design-system.md) | Design System Port | 1 | WO-001 |
| [WO-003](work-orders/WO-003-data-layer.md) | Data Layer | 1 | WO-001 |
| [WO-004](work-orders/WO-004-catalog.md) | Catalog Page | 2 | WO-002, WO-003 |
| [WO-005](work-orders/WO-005-edition.md) | Edition Detail Page | 3 | WO-004 |
| [WO-006](work-orders/WO-006-item-detail.md) | Item Detail Page | 3 | WO-004, WO-005 |

---

## Tech Stack

| Layer | Choice | Notes |
|---|---|---|
| Framework | Next.js 16 (App Router) | SSR/SSG via Server Components |
| Language | TypeScript | Strict mode |
| Styling | Tailwind CSS v4 | `@theme` OKLCH tokens from PandaTrack |
| Components | CVA (class-variance-authority) | Variant recipes |
| Data | `fs.readFileSync` on `data/items.jsonl` | No API routes; direct server read |
| Images | Symlink `public/images → ../../data/images/` | Python pipeline unchanged |
| State (filters) | URL search params | `useSearchParams` + `router.replace()` |
| Dark mode | `data-theme` attribute on `<html>` | localStorage persistence |
| React | 19.x | Server Components default |

---

## Key Constraints

1. **No API routes.** All data loading happens in Server Components via `fs.readFileSync`.
2. **Feedback (👎) stays in `web/index.html`** for now. Not ported.
3. **Python pipeline unchanged.** Scripts write to `data/items.jsonl` and `data/images/` exactly as today.
4. **Symlink for images.** `web-next/public/images` → `../../data/images/`. Next.js serves `/images/filename.jpg`.
5. **`slug` field required.** Every item needs a `slug` before the item detail page can go live (see FRD-006).
6. **DB-migration-ready.** `edition_key`, `slug`, `cluster_key` are first-class fields → survive SQLite/Postgres move.

---

## Folder Structure (target)

```
web-next/
├── app/
│   ├── globals.css              ← design system (ported from PandaTrack)
│   ├── layout.tsx               ← root layout, dark/light mode
│   ├── page.tsx                 ← catalog (Server Component)
│   ├── edition/
│   │   └── [editionKey]/
│   │       └── page.tsx         ← edition detail (Server Component)
│   └── item/
│       └── [slug]/
│           └── page.tsx         ← item detail (Server Component)
├── components/
│   ├── core/                    ← Typography, Heading, Button, Chip, Badge, Icon
│   ├── modules/                 ← EditionCard, ItemCard, ImageCarousel, SignalChip
│   ├── catalog/                 ← CatalogGrid, SidebarFilters, SortBar, Pagination
│   ├── edition/                 ← EditionHeader, VolumeGrid
│   └── item/                   ← ItemHero, MetaTable, SourcesList
├── lib/
│   ├── data.ts                  ← JSONL reader, cluster grouping
│   ├── types.ts                 ← TypeScript types
│   ├── slugs.ts                 ← lookupBySlug(), lookupEdition()
│   ├── filters.ts               ← filterClusters(), sort, paginate
│   └── styles.ts                ← cn() utility
├── public/
│   └── images → ../../data/images/   ← symlink
└── package.json
```

---

*Last updated: 2026-05-27 (initial documentation)*
