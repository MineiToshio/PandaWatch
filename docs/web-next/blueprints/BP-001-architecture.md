# BP-001: Architecture Overview

**Version:** 1.0  
**Status:** Draft  
**Author:** Architecture session 2026-05-27  
**Related FRDs:** All

---

## Purpose

Describe the overall technical architecture of the PandaWatch App (web-next/).
This blueprint answers: how do the pieces fit together? What are the boundaries
between server and client? How does data flow from JSONL to rendered HTML?

---

## Architecture Overview

```
┌────────────────────────────────────────────────────────────────────┐
│                        PYTHON PIPELINE                              │
│  manga_watch.py → items.jsonl → data/images/                       │
│  (unchanged, writes to disk, runs independently of the web app)    │
└─────────────────────────────┬──────────────────────────────────────┘
                              │ fs (disk)
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│                     NEXT.JS APP (web-next/)                        │
│                                                                     │
│  BUILD TIME                    REQUEST TIME (dev) / STATIC (prod)  │
│  ──────────                    ──────────────────────────────────  │
│  generateStaticParams()        Server Component                     │
│    → all edition_keys          → fs.readFileSync(items.jsonl)      │
│    → all slugs                 → filterClusters(searchParams)      │
│                                → render HTML                        │
│                                                                     │
│  CLIENT (browser)                                                   │
│  ─────────────                                                      │
│  SidebarFilters (Client)       → router.replace(newSearchParams)   │
│  ImageCarousel (Client)        → useState(carouselIndex)           │
│  ThemeToggle (Client)          → localStorage + data-theme attr    │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    Browser renders HTML
```

---

## Key Architectural Decisions

### ADR-001: Server Components by default, Client Components only for interaction

**Decision:** All pages and most components are Server Components. Client Components
(`"use client"`) are used only when browser APIs or React state are needed:
- `SidebarFilters` — `useSearchParams`, `router.replace`
- `ImageCarousel` — `useState` for current image index
- `ThemeToggle` — `localStorage`, click handler
- `MobileDrawer` — `useState` for open/close

**Rationale:** Server Components eliminate client-side JS for rendering, reduce
bundle size, and enable direct server-side data access without API routes.

**Consequence:** No `useEffect`, no `fetch()` from the browser for data loading.

---

### ADR-002: No API routes

**Decision:** `app/api/` does not exist in this app. Data is read directly from
disk in Server Components using `fs.readFileSync`.

**Rationale:** The app is single-user/local for now. Adding an API layer would
introduce unnecessary complexity and network latency. When the app goes multi-user
(SQLite/Postgres), the data access layer (`lib/data.ts`) is the only file that
changes — pages and components are untouched.

**Consequence:** The feedback (👎) endpoint stays in `serve.py` (Python) for now.
When the Next.js app needs write access, a proper API route or Server Action will
be added at that point.

---

### ADR-003: Filter state in URL search params

**Decision:** All filter and sort state is encoded in URL search params. The Server
Component reads `searchParams` prop. The Client Component `SidebarFilters` calls
`router.replace()` to update the URL.

**Rationale:**
- Shareable / bookmarkable URLs
- Browser back/forward works as expected
- No client-side state management library needed
- SSR renders the correct filtered view on first load

**Consequence:** Every filter change causes a soft navigation (URL change +
Server Component re-render). This is ~50ms in production — acceptable.

---

### ADR-004: Static generation for item and edition pages

**Decision:** Item detail pages (`/item/[slug]`) and edition pages
(`/edition/[editionKey]`) are statically generated at build time via
`generateStaticParams()`.

**Rationale:** The corpus is updated by running the Python scraper (not continuously).
Static pages are served instantly with zero server computation per request. After
each scraper run, `next build` re-generates the pages.

**Consequence:** After a scrape run, `next build` must be re-run to pick up new
items/editions. Acceptable for the current single-user workflow (it's part of
the `scrape_*.sh` pipeline). When real-time updates are needed (multi-user), switch
to ISR (Incremental Static Regeneration) or dynamic rendering.

---

### ADR-005: Images via symlink in public/

**Decision:** `web-next/public/images` is a symlink to `../../data/images/`. Next.js
serves files in `public/` statically at the root. So `/images/abc123.jpg` maps to
`data/images/abc123.jpg`.

**Rationale:** The Python scraper writes images to `data/images/`. Symlinking means
zero duplication — there is only one copy of each image on disk. The Python pipeline
does not change.

**Consequence:** The symlink must be created once as part of project setup (WO-001).
Deploying to a server requires either keeping the symlink or copying the images folder.
For the cloud deploy (Cloudflare R2, future), images will be served from R2 and this
symlink becomes unnecessary.

---

### ADR-006: Tailwind v4 with OKLCH design tokens

**Decision:** Use Tailwind CSS v4's `@theme` directive with OKLCH color tokens,
ported from PandaTrack. Pink accent override for PandaWatch branding.

**Rationale:** PandaTrack's design system is already production-tested. OKLCH enables
perceptually uniform color manipulation (lightness/chroma/hue) and correct dark mode
interpolation. Reusing the same system means PandaWatch App and PandaTrack look like
siblings — intentional, as they may merge in the future.

---

### ADR-007: Solo mostrar items estandarizados (`standardized_at` filter)

**Decision:** `loadClusters()` in `lib/data.ts` filters out any item whose
`standardized_at` field is empty/null before grouping into clusters. Only items
that have passed through the `/watch-standardize-catalog` skill are visible in the app.

**Rationale:** Items freshly scraped by `manga_watch.py` may have rough
`series_key`, incorrect `edition_key`, or missing `slug` values — the scraper's
heuristic pass is intentionally conservative and leaves LLM-verification to the
skill. Displaying unverified items would contaminate the catalog with uncurated
entries and break `generateStaticParams()` (which iterates all slugs/editionKeys).

**Consequence:** After each scrape run, the operator must invoke `/watch-standardize-catalog`
for newly scraped items to appear in the app. This is by design: the skill is the
gate between raw data and curated presentation.

---

## Directory Structure

```
web-next/
├── app/                        ← Next.js App Router
│   ├── globals.css             ← Design system (Tailwind v4 @theme)
│   ├── layout.tsx              ← Root layout (html, body, Header)
│   ├── page.tsx                ← Catalog — Server Component
│   ├── edition/
│   │   └── [editionKey]/
│   │       └── page.tsx        ← Edition detail — Server Component
│   └── item/
│       └── [slug]/
│           └── page.tsx        ← Item detail — Server Component
│
├── components/
│   ├── core/                   ← Atomic components (Button, Chip, Badge, etc.)
│   ├── modules/                ← Compound components used across pages
│   ├── catalog/                ← Components specific to the catalog page
│   ├── edition/                ← Components specific to the edition page
│   └── item/                   ← Components specific to the item detail page
│
├── lib/
│   ├── data.ts                 ← JSONL reader + cluster grouping + filters
│   ├── types.ts                ← TypeScript types (Item, Cluster, Facets, etc.)
│   ├── slugs.ts                ← Lookup functions by slug / editionKey
│   ├── filters.ts              ← filterClusters, sortClusters, paginate
│   └── styles.ts               ← cn() utility
│
└── public/
    └── images → ../../data/images/   ← symlink
```

---

## Data Flow Summary

```
items.jsonl (disk)
      │
      ▼ fs.readFileSync (Server Component / build time)
lib/data.ts::loadItems()       ← parse JSONL lines → Item[]
      │
      ▼
lib/data.ts::groupByClusters() ← group by cluster_key → Cluster[]
      │
      ├──▶ catalog/page.tsx
      │       │ filterClusters(searchParams)
      │       │ sortClusters(sort)
      │       │ paginate(page, 60)
      │       └──▶ <CatalogGrid clusters={page} />
      │
      ├──▶ edition/[editionKey]/page.tsx
      │       │ loadEditionClusters(editionKey)
      │       └──▶ <VolumeGrid clusters={...} />
      │
      └──▶ item/[slug]/page.tsx
              │ clusterBySlug(slug)
              └──▶ <ItemHero cluster={...} />
                   <ImageCarousel images={...} />  ← Client Component
                   <MetaTable item={...} />
                   <SourcesList items={...} />
```

---

## Dependency Graph

```
WO-001 (scaffold)
    └── WO-002 (design system)
            └── WO-003 (data layer)
                    └── WO-004 (catalog)
                            └── WO-005 (edition detail)
                            └── WO-006 (item detail)
```
