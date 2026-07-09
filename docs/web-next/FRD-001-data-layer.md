# FRD-001: Data Layer

**Version:** 1.0  
**Status:** Draft  
**Author:** Architecture session 2026-05-27  
**Related:** [BP-003](blueprints/BP-003-data-flow.md), [WO-003](work-orders/WO-003-data-layer.md)

---

## Overview

The data layer reads `data/items.jsonl` on the server and exposes typed functions
consumed exclusively by Server Components. No API routes. No client-side fetch of
the JSONL file (the Alpine.js app did a client-side `fetch("../data/items.jsonl")`
— that pattern is replaced entirely by server-side reads).

---

## Problem Statement

The Alpine.js dashboard loaded the full JSONL in the browser (~1–3 MB uncompressed),
parsed it client-side, and ran all filtering/grouping in JavaScript. This works for
a single local user but:
- Sends the full dataset on every page load (no caching, no incremental)
- Cannot be deployed as a multi-user service without an API layer
- Is not SEO-friendly (content rendered after JS executes)

The Next.js app reads and processes the data on the server, emits pre-rendered HTML,
and only sends the relevant slice of data to the browser.

---

## User Stories

- As a **developer**, I want a typed API over items.jsonl so I don't repeat JSONL
  parsing logic in every page.
- As a **Server Component**, I want to call `loadClusters()` and get a fully grouped,
  typed result ready for rendering.
- As a **filter component**, I want pre-computed facet counts (how many items per
  country, per signal type, etc.) so I can show badges on filter options.

---

## Functional Requirements

### FR-1: JSONL reading

The function `loadClusters()` reads `data/items.jsonl` synchronously via
`fs.readFileSync`. Each line is parsed as JSON and typed as `Item`. Lines that fail
JSON parsing are silently skipped with a `console.warn`.

**Cache behavior:**
- In development: file is re-read on every request (hot reload)
- In production (static export or `next start`): Next.js caches the result of the
  first call within the request lifecycle. For full-static builds (`next export`),
  data is baked in at build time.

### FR-1b: Filtro por `standardized_at`

Solo se cargan items con `standardized_at` no vacío. Items sin este campo (scrapeados pero aún
no procesados por el skill `/watch-standardize-catalog`) **no aparecen en el app**.

**Rationale:** Garantiza que `edition_key`, `series_key`, `title` estandarizado y `slug` están
correctamente asignados antes de mostrar el item. Sin este filtro, items recién scrapeados con
series_key crudos o edition_keys incorrectos contaminarían las rutas estáticas generadas por
`generateStaticParams()`.

**Consecuencia operativa:** Después de cada scrape, correr `/watch-standardize-catalog` para que los
items nuevos aparezcan en la app.

### FR-2: Cluster grouping

Items are grouped by `cluster_key`. The result type is `Cluster`:

```ts
type Cluster = {
  clusterKey: string          // raw cluster_key from JSONL
  slug: string                // URL-safe, unique (from slug field)
  canonical: Item             // most complete item in the cluster (completeness: ISBN > image)
  items: Item[]               // all items in the cluster (all sources)
  editionKey?: string         // from canonical.edition_key
  editionDisplay?: string     // from canonical.edition_display
  seriesDisplay?: string      // from canonical.series_display
  volume?: string             // from canonical.volume
  volumeCount: number         // distinct volumes in this cluster group*
  signalTypes: string[]       // union of signal_types across all items
  countries: string[]         // distinct countries
  publishers: string[]        // distinct publishers
  languages: string[]         // distinct languages
}
```

*`volumeCount` is used to control the "stack" CSS effect (1 leaf / 2 leaves / 3 leaves).

### FR-3: Edition grouping

`loadEditionClusters(editionKey: string): Cluster[]` returns all clusters that share
the same `edition_key`, sorted by volume number ascending. Used by the edition detail page.

### FR-3b: Catalog edition grouping

`groupByEdition(clusters: Cluster[]): Cluster[]` collapses clusters that share the
same `edition_key` into a single representative entry for the catalog home page.

- Preserves the sort order of the input array (a cluster's position is determined by
  where the first cluster with its `edition_key` appeared).
- For each edition group: `volumeCount` = number of clusters in the group;
  `canonical` = the most complete cluster's canonical (`completeness()`: ISBN > image),
  promoted together with its `slug` **and `volume`** (cover and volume stay coherent);
  `signalTypes`, `countries`, `publishers`, `languages` are the union across all clusters.
- Standalone clusters (no `edition_key`) are passed through unchanged.

Called in `app/page.tsx` **after** `filterClusters()` and `sortClusters()`, so:
- Facets are always computed from the unfiltered full corpus.
- Filtering happens at the cluster level (correct).
- `volumeCount` reflects how many filtered volumes each edition has.

### FR-4: Slug lookup

`clusterBySlug(slug: string): Cluster | null` returns the cluster whose canonical
item has `slug === slug`. Returns `null` if not found (triggers `notFound()` in the
page).

### FR-5: Edition key lookup

`allEditionKeys(): string[]` returns all distinct `edition_key` values present in the
corpus. Used by `generateStaticParams()` in the edition detail page for static generation.

`allSlugs(): string[]` returns all distinct `slug` values. Used by
`generateStaticParams()` in the item detail page.

### FR-6: Filtering

`filterClusters(clusters: Cluster[], params: FilterParams): Cluster[]` applies
all active filters and returns matching clusters. Filters:

| Param | Type | Logic |
|---|---|---|
| `q` | string | Match normalizado (lowercase + NFD sin diacríticos) sobre `Cluster.searchText` (= `title + title_original + series_display + publishers + isbn-sin-guiones`, precomputado en `buildCluster`) + aliases de serie. **Multi-token AND**: el query se tokeniza por espacios y todos los tokens deben aparecer; un token ISBN-like (10-13 dígitos) se colapsa a dígitos. CJK intacto. Ver auditoría Fable 2026-07-08 #1/#2. |
| `country` | string[] | ANY match in cluster.countries |
| `language` | string[] | ANY match in cluster.languages |
| `publisher` | string[] | ANY match in cluster.publishers |
| `product_type` | string[] | ANY match across cluster items |
| `source_class` | string[] | ANY match across cluster items |
| `signal_types` | string[] | ALL selected signals must be present in cluster.signalTypes |
| `rarity` | string[] | ANY match on `canonical.rarity` |
| `only_limited` | boolean | At least one of `limited`, `special_edition`, `collector`, `lore_edition`, `variant_cover` (+ artbook/kanzenban/deluxe/box_set/retailer_exclusive) in signalTypes |

(`min_score` se eliminó junto con el score — precios/score fuera del pipeline, 2026-06-11.)

`parseFilterParams()` sanea searchParams hostiles: params escalares repetidos
(`?q=a&q=b` llega como array) toman el primer valor, `page` no entero/negativo cae a 1,
`sort` desconocido cae a `date_desc`. Antes un `q` repetido crasheaba la home con 500.

### FR-7: Sorting

`sortClusters(clusters: Cluster[], sort: SortKey): Cluster[]`

| Sort key | Logic |
|---|---|
| `date_desc` (default) | `canonical.release_date` descending (items without date go last) |
| `date_asc` | `canonical.release_date` ascending |
| `title_asc` | `canonical.title` alphabetical |
| `title_desc` | `canonical.title` reverse alphabetical |

(`score_desc`/`score_asc` se eliminaron junto con el score.) Las fechas se comparan vía
`sortableDate()` (lib/format.ts), que normaliza el formato legacy `DD/MM/YYYY` a ISO —
sin eso un item `31/10/2023` ordenaba como el más reciente del catálogo. Los formatos
parciales reales del corpus (`YYYY`, `YYYY-MM`) ordenan bien como string.

### FR-8: Pagination

`paginate(clusters, page, pageSize = 60)` returns `{ items, total, pages, page }`.
Page is 1-indexed. `total` is the count before pagination (used for "N ediciones" label).

### FR-9: Facet computation

`buildFacets(clusters: Cluster[]): Facets` computes the filter option lists with counts:

```ts
type Facets = {
  countries: { value: string; count: number }[]
  languages: { value: string; count: number }[]
  publishers: { value: string; count: number }[]
  signalTypes: { value: string; count: number }[]
}
```

Facets are computed from the **unfiltered** full corpus so counts don't change as
filters are applied (stable facets UX pattern). `productTypes`/`sourceClasses`/`scoreRange`
se eliminaron (sin UI que los consuma). La home recorta los facets a lo que la UI muestra
(top 12 publishers, top 8 languages) ANTES de serializarlos al client component.

**Cacheado (auditoría Fable 2026-07-08 #6):** los facets globales se computan **una
vez** dentro de `DataCache` (invalidados por mtime, igual que `bySlug`) y se sirven
vía `loadFacets()`. La home es `force-dynamic` (para leer searchParams por request);
antes recalculaba `buildFacets` sobre los ~12.8k clusters en cada keystroke/toggle.
`buildFacets(clusters)` sigue exportado para subconjuntos arbitrarios.

---

## Non-Functional Requirements

- **Performance:** `loadClusters()` must complete in < 200ms for a corpus of 10k items.
  JSONL parsing of 10k lines takes ~20ms; cluster grouping ~30ms. Total well under budget.
- **Caching:** el cache de módulo se invalida por **mtime** del JSONL (vale también en dev:
  sin esto cada request re-parseaba el corpus). Junto al cache se construyen índices
  `Map` (`bySlug`, `byEdition`, `bySeries`, series `byKey`) + los `facets` globales — los
  lookups por página dejan de ser scans O(n) durante `generateStaticParams` (~23k páginas).
  `bySeries` (auditoría Fable 2026-07-08 #23) elimina el scan lineal del corpus que
  `loadSeriesEditions`/`seriesCache` hacían por cada una de las ~3.7k páginas de serie.
  `ALIASES_PATH` y `NEXT_PUBLIC_IMAGE_BASE_URL` son env overrides coherentes con
  `ITEMS_PATH` para deploys (ver README → Deploy).
- **Type safety:** All functions are fully typed. No `any`. `Item` type mirrors the
  `items.jsonl` schema documented in `CLAUDE.md`.
- **Error handling:** corrupted JSONL lines and rows without `cluster_key` are skipped
  **with a `console.warn` count** (never silently). A missing `items.jsonl` throws a
  descriptive error. Duplicate slugs (pipeline invariant violation, FRD-006 FR-2) warn
  and keep the first cluster instead of silently shadowing. `ITEMS_PATH` env var
  overrides the default `../data/items.jsonl` location.

---

## Out of Scope

- Mutations (write to items.jsonl). The app is read-only. Feedback (👎 button) stays in
  the Python `serve.py` server for now.
- Real-time updates. The data is static per build/request.
- Search ranking or full-text search beyond substring matching.

---

## Acceptance Criteria

- [ ] `loadClusters()` returns correctly typed `Cluster[]` from the real `data/items.jsonl`
- [ ] Cluster grouping produces same result as Alpine.js `dedupByUrl()` + `editions` getter
- [ ] `filterClusters` with `q="berserk"` returns only berserk items
- [ ] `filterClusters` with `signal_types=["box_set"]` returns only box set items
- [ ] `paginate` with page=2 and pageSize=60 returns items 61–120
- [ ] `allSlugs()` returns same count as distinct `slug` values in items.jsonl
- [ ] Function resolves in < 200ms on the local machine

---

## Dependencies

- `data/items.jsonl` must exist (populated by Python scraper)
- `slug` field must be populated in items.jsonl (see FRD-006)
