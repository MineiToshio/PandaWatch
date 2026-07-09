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
- Usa el design system **PandaWatch** (tokens bamboo/ink en hex, light-only — el
  handoff bundle de WO-002; NO los tokens OKLCH de PandaTrack)
- Will be the base for a future multi-user deployment (la migración a DB del
  items.jsonl está planificada; `lib/data.ts` es la única frontera de acceso a datos)

---

## Document Index

### FRDs — Functional Requirements

| ID | Title | Status |
|---|---|---|
| [FRD-001](FRD-001-data-layer.md) | Data Layer | Implemented |
| [FRD-002](FRD-002-design-system.md) | Design System | Implemented |
| [FRD-003](FRD-003-catalog.md) | Catalog Page | Implemented |
| [FRD-004](FRD-004-edition-detail.md) | Edition Detail Page | Implemented |
| [FRD-005](FRD-005-item-detail.md) | Item Detail Page | Implemented |
| [FRD-006](FRD-006-slug-generation.md) | Slug Generation | Implemented |
| [FRD-007](FRD-007-series-highlights.md) | Series Highlights & Series Page | Implemented |
| [FRD-008](FRD-008-seo-discoverability.md) | SEO & Discoverability | Implemented |

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
| [WO-007](work-orders/WO-007-image-lightbox.md) | Image Lightbox | 4 | WO-006 |
| [WO-008](work-orders/WO-008-series-page.md) | Series Highlights & Series Page | 4 | WO-004, WO-005, WO-006 |
| [WO-009](work-orders/WO-009-seo-foundations.md) | SEO Foundations (site URL, robots, sitemap, manifest) | 5 | WO-004, WO-005, WO-006, WO-008 |
| [WO-010](work-orders/WO-010-metadata-og.md) | Rich Metadata (canonical, OG, Twitter) | 5 | WO-009, WO-011 |
| [WO-011](work-orders/WO-011-entity-descriptions.md) | Per-entity Descriptions (template content) | 5 | WO-003 |
| [WO-012](work-orders/WO-012-structured-data.md) | Structured Data (JSON-LD) | 5 | WO-009, WO-010, WO-011 |

---

## Tech Stack

| Layer | Choice | Notes |
|---|---|---|
| Framework | Next.js 16 (App Router) | SSR/SSG via Server Components |
| Language | TypeScript | Strict mode |
| Styling | CSS vars + clases `.pw-*` en `app/globals.css` | Tailwind v4, CVA y tailwind-merge **desinstalados** 2026-07-08 (auditoría #14, 0 usos reales fuera de 2 utility classes en `CountryFlag`) — ver "Dirección de estilos" abajo |
| Data | `fs.readFileSync` on `data/items.jsonl` | No API routes; direct server read |
| Images | Symlink `public/images → ../../data/images/` | Python pipeline unchanged |
| State (filters) | URL search params | `lib/useCatalogParams.ts` (hook único, auditoría #11) — `set`/`toggle`/`clearAll` sobre la URL viva, envueltos en `useTransition` |
| Fonts | `next/font/google` (self-hosted) | Space Grotesk / DM Sans / JetBrains Mono vía CSS vars |
| React | 19.x | Server Components default |

(El dark mode del stack original de PandaTrack NO se portó — el design system
PandaWatch es light-only.)

---

## Key Constraints

1. **No API routes.** All data loading happens in Server Components via `fs.readFileSync`.
2. **Feedback (👎) stays in `web/index.html`** for now. Not ported.
3. **Python pipeline unchanged.** Scripts write to `data/items.jsonl` and `data/images/` exactly as today.
4. **Symlink for images.** `web-next/public/images` → `../../data/images/`. Next.js serves `/images/filename.jpg`.
5. **`slug` field required.** Every item needs a `slug` before the item detail page can go live (see FRD-006).
6. **DB-migration-ready.** `edition_key`, `slug`, `cluster_key` are first-class fields → survive SQLite/Postgres move.
7. **Client `useSearchParams()` must be wrapped in `<Suspense>`.** `Header` → `SearchBar`
   (a `'use client'` component using `useSearchParams()`) renders on every page. Detail
   routes (`/item`, `/edition`, `/series`) have `generateStaticParams`, so `next build`
   prerenders them — and an unwrapped `useSearchParams()` aborts that pass
   (`missing-suspense-with-csr-bailout`). `SearchBar` is wrapped in `<Suspense>` in
   `Header.tsx`. `next dev` compiles on demand and does **not** surface this — only a full
   `npm run build` does. Run `npm run build` before deploying, not just `next dev`.

---

## Deploy — estrategia de datos e imágenes (auditoría Fable 2026-07-08 #4)

> **Estado: vía documentada y habilitada por env vars; el deploy real NO está hecho.**

El objetivo del proyecto es un frontend **público** en Vercel / Cloudflare Pages, pero
hoy la app sólo corre en la máquina del owner porque **los datos y las imágenes están
gitignored** (`data/items.jsonl`, `data/series_aliases.json`, `data/images/`) y las
imágenes se sirven por un **symlink** (`public/images → ../../data/images/`). En un clone
limpio de CI/Vercel esos paths no existen: `readRawItems()` lanzaría en build y el symlink
apuntaría a la nada. Es SSG puro (sin DB ni API routes), así que la solución es de
**abastecimiento de datos en build**, no de arquitectura runtime.

### Qué sube el build (artefactos)

1. **Corpus** — `items.jsonl` (~decenas de MB) + `series_aliases.json`. No están en git;
   el paso `prebuild` los descarga (o los copia) a una ruta accesible y se apunta con
   env vars:
   - `ITEMS_PATH` → ruta absoluta al `items.jsonl` descargado.
   - `ALIASES_PATH` → ruta al `series_aliases.json` (default: junto al items.jsonl).

   Fuente sugerida: un artefacto versionado (Vercel Blob / R2 / release asset) que el owner
   publica tras cada corrida del pipeline. El build baja la copia más reciente en `prebuild`.

2. **Imágenes** — el espejo local (~1.64 GB, AVIF Q60 ≤1600px ya pre-optimizado) **no** viaja
   en el repo ni conviene meterlo en el bundle. Van a un **bucket R2** propio ("Image storage
   Fase 2" en CLAUDE.md; entra en el free tier de 10 GB porque ya está pre-optimizado — R2 no
   transforma). Se apunta con:
   - `NEXT_PUBLIC_IMAGE_BASE_URL` → base pública del bucket (p.ej. `https://images.watch.pandatrack.app`).

   Con esa var seteada, `CoverImage`, `ogImage()` (OG/Twitter) y el `image` del JSON-LD
   resuelven `images[0].local` contra el bucket en lugar del symlink. La `src` del bucket es
   absoluta → `CoverImage` la sirve por `<img>` plano (next/image no optimiza hosts sin
   allowlist, y no hace falta: el AVIF ya está optimizado). **Sin la var, el comportamiento
   local es idéntico al de hoy** (symlink `/images/...` vía next/image).

### Env vars del deploy (ver `.env.example`)

| Var | Para qué | Local |
|---|---|---|
| `NEXT_PUBLIC_SITE_URL` | Origin público (sitemap, canonical, OG) | unset → localhost |
| `ITEMS_PATH` | Ruta al corpus JSONL | unset → `../data/items.jsonl` |
| `ALIASES_PATH` | Ruta a `series_aliases.json` | unset → junto al items.jsonl |
| `NEXT_PUBLIC_IMAGE_BASE_URL` | Base del bucket de imágenes | unset → symlink `/images/` |

### Qué falta para el deploy real (NO hecho acá)

- Publicar el artefacto de corpus (elegir Vercel Blob vs R2 vs release asset) y escribir el
  script `prebuild` que lo baja y setea `ITEMS_PATH`/`ALIASES_PATH`.
- Subir el espejo `data/images/` al bucket R2 y setear `NEXT_PUBLIC_IMAGE_BASE_URL`.
- Setear `NEXT_PUBLIC_SITE_URL` en Vercel Production y validar en Google Rich Results Test.

Hasta que eso exista, un deploy a Vercel **fallaría en build** — el "pending" NO está a un
env var de distancia; requiere abastecer corpus + imágenes primero.

---

## Folder Structure (target)

```
web-next/
├── app/
│   ├── globals.css              ← design system (ported from PandaTrack)
│   ├── layout.tsx               ← root layout, dark/light mode
│   ├── page.tsx                 ← catalog (Server Component)
│   ├── series/
│   │   └── [seriesKey]/
│   │       └── page.tsx         ← series detail (Server Component, SSG — FRD-007)
│   ├── edition/
│   │   └── [editionKey]/
│   │       └── page.tsx         ← edition detail (Server Component)
│   └── item/
│       └── [slug]/
│           └── page.tsx         ← item detail (Server Component)
├── components/
│   ├── modules/                 ← ItemCard, CoverImage, SearchBar, Header, BackLink,
│   │                              NavigationTracker, RarityBadge, SignalChip, CountryFlag
│   ├── catalog/                 ← CatalogGrid, EditionCard, SidebarFilters, SortBar,
│   │                              Pagination, CatalogControls, EmptyState
│   ├── series/                  ← SeriesCard, SeriesHighlights, SeriesHeader (FRD-007)
│   ├── edition/                 ← EditionHeader, VolumeGrid
│   ├── item/                    ← ItemHero, ImageCarousel, MetaTable, SourcesList, ExtrasSection
│   └── seo/                     ← JsonLd
├── lib/
│   ├── data.ts                  ← JSONL reader, cluster grouping, lookups (Maps), sitemap helpers
│   ├── types.ts                 ← TypeScript types
│   ├── filters.ts               ← parseFilterParams(), filterClusters(), sort, paginate
│   ├── format.ts                ← formatDate() (4 formatos de fecha), sortableDate()
│   ├── images.ts                ← dedupeImages()/imageKey() (fuente única de dedup)
│   ├── seo.ts                   ← siteUrl(), absoluteUrl(), seriesPath/editionPath/itemPath,
│   │                              decodeRouteParam(), ogImage()
│   ├── jsonld.ts                ← schema.org builders
│   ├── descriptions.ts          ← per-entity template descriptions
│   ├── vocab.ts                 ← vocabulario único de señales/tipos de edición (auditoría #12)
│   ├── useCatalogParams.ts      ← hook único de mutación de URL (auditoría #11)
│   └── facets.ts                ← productTypeFacet() (auditoría #21)
├── app/{robots,sitemap,manifest,not-found,error}.tsx   ← SEO + estados de sistema (FRD-008, auditoría #7)
├── public/
│   └── images → ../../data/images/   ← symlink
└── package.json
```

(`components/core/` se eliminó 2026-06-12: era código muerto sin consumidores.
`lib/slugs.ts` nunca existió — los lookups viven en `lib/data.ts`. `lib/styles.ts`
[`cn()`] se eliminó 2026-07-08 junto con `tailwind-merge`/`clsx` — auditoría #14.)

---

*Last updated: 2026-06-12 (revisión integral post-implementación: se eliminó el mecanismo
`?from=` — las ~19,600 páginas de detalle vuelven a ser SSG reales (`dynamicParams=false`),
links internos limpios crawleables, back-state en sessionStorage; fechas parciales/legacy
bien mostradas y ordenadas; saneo de searchParams hostiles; rutas con claves no-ASCII
percent-encoded + decode; sitemap con lastModified; JSON-LD sin Offer/bookFormat;
next/font self-hosted; RarityBadge/dedupeImages unificados; `components/core/` eliminado;
39 tests. Pending: set `NEXT_PUBLIC_SITE_URL` in Vercel Production, then validate in
Google Rich Results Test.)*

*Actualizado 2026-07-08 (paquete H1-webnext-core de la auditoría Fable): búsqueda por
**editorial** e **ISBN** + normalización de acentos + tokens AND (`Cluster.searchText`
precomputado); facets globales e índice `bySeries` cacheados en `DataCache` (auditoría
#6/#23); JSON-LD `/item` = `Book`/`CreativeWork`, **sin `Product`**, imagen local-first
(auditoría #5); vía de deploy documentada + habilitada por env vars (`ITEMS_PATH`,
`ALIASES_PATH`, `NEXT_PUBLIC_IMAGE_BASE_URL`) SIN deployar (auditoría #4); tests de
`descriptions`/`jsonld`/`seo` + búsqueda (54→95). Ver la sección "Deploy" de arriba.)*

---

## Dirección de estilos (auditoría #14, 2026-07-08)

**CSS vars + clases `.pw-*` en `app/globals.css`.** Tailwind v4,
`class-variance-authority` y `tailwind-merge` se desinstalaron — su único uso
real en todo el árbol era `CountryFlag.tsx` (2 utility classes: `inline-flex
items-center gap-1` y `text-xs`), reemplazado por una clase `.pw-country-flag`.
`clsx` se desinstaló junto con ellos (mismo único consumidor).

- El design system ya definía clases semánticas (`.pw-h1`…`.pw-caption`) que
  estaban sin uso — la dirección elegida las adopta en vez de introducir un
  segundo sistema.
- **No se migró todo el árbol.** La mayoría de los componentes sigue en
  inline `style={{}}` — sólo se consolidaron a `.pw-*` los estilos repetidos
  de los componentes que este work order YA tocaba (`SidebarFilters` →
  `.pw-filter-section`/`.pw-check-row*`, home → `.catalog-h1`, el drawer/
  lightbox → `.pw-drawer-dialog`/`.pw-lightbox-dialog`). Migrar el resto
  (EditionCard, ItemCard, SeriesCard, etc.) queda para cuando se toquen por
  otro motivo — la regla es oportunista, no un rewrite.
- **Próximo candidato natural si se retoma**: los `<style>` embebidos en
  componentes (`ItemHero.tsx`, `VolumeGrid.tsx`) para media queries — inline
  `style={{}}` no soporta `@media`, por eso ya conviven 3 mecanismos
  (inline / `<style>` embebido / `globals.css`). Documentado, no resuelto acá.

## Assets — panda-mark y compresión (auditoría #3, 2026-07-08)

`public/panda-mark.png` (1024×1024, 2.10 MB) se servía en el `<img>` de 32×32
del header en TODAS las páginas sin pasar por el optimizer de Next (es un
`<img>` plano, a propósito — ver `Header.tsx`). Reemplazado por
`public/panda-mark-64.png` (64×64, ~8 KB — 2x para retina), generado con
`sips -Z 64`. `og-default.png`/`icon-512.png`/`icon-192.png` se recomprimieron
con ImageMagick (`png:compression-level=9`, lossless) — ~10% menos sin
herramientas de quantización (pngquant/oxipng no estaban disponibles en la
máquina; `sips`/ImageMagick sí). Si se instala pngquant más adelante, esos
tres archivos tienen más margen.

## Tests de componentes (auditoría #20, 2026-07-08)

`vitest.config.ts` corre en `environment: 'jsdom'` (vitest 4.1.7 ya no trae
`environmentMatchGlobs` per-glob ni el docblock `@vitest-environment` de v3 —
se evaluó y no existe en esta versión; ver `node_modules/vitest`). jsdom
sigue siendo Node.js completo por debajo (fs, etc. intactos), así que los
tests de `lib/` puros no se vieron afectados por el cambio global.
`__tests__/setup.ts` registra `cleanup()` de `@testing-library/react` después
de cada test (si no, el DOM se acumula entre `it()` del mismo archivo y
`getByRole`/`getByText` empiezan a matchear duplicados). Nuevas devDependencies
(permitidas por el work order): `jsdom`, `@testing-library/react`,
`@testing-library/jest-dom`.
