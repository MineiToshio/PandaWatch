# FRD-008: SEO & Discoverability

**Version:** 1.0
**Status:** Draft
**Author:** Architecture session 2026-06-06
**Related:** [BP-002](blueprints/BP-002-url-routing.md), [FRD-001](FRD-001-data-layer.md), [FRD-004](FRD-004-edition-detail.md), [FRD-005](FRD-005-item-detail.md), [FRD-007](FRD-007-series-highlights.md)

---

## Overview

Make the public Next.js frontend (`web-next/`) discoverable by:
- **Web search engines** (Google, Bing) — crawlability, sitemap, rich results.
- **LLM crawlers / answer engines** (ChatGPT/GPTBot, ClaudeBot, PerplexityBot,
  Google-Extended, etc.) — clean HTML, structured data, real text content.
- **Social platforms** — Open Graph / Twitter Cards.

Today the app renders crawlable server HTML and has stable, human-readable slugs
(FRD-006) — a strong base — but is missing every discovery surface: no sitemap, no
robots, no structured data, no canonical URLs, no per-entity text content, and no
configured site URL. This FRD closes those gaps.

---

## Problem Statement

1. **No crawl entry points.** Without `sitemap.xml` + `robots.txt`, the ~10k item /
   edition / series pages depend entirely on incidental link discovery.
2. **Thin content.** Only ~30% of items have a `description`; series and edition pages
   have none. Pages that are mostly an image + metadata are "thin content" — poorly
   ranked and useless as an LLM source.
3. **No structured data.** Search engines and LLMs can't reliably extract the
   product/book facts (ISBN, author, publisher, price, edition type) that this catalog
   is uniquely good at.
4. **No absolute base URL.** Canonical tags, sitemap entries, and OG `url`/image fields
   all require an absolute origin that isn't configured anywhere.
5. **Filter URLs are unbounded.** The home page is `force-dynamic` over `searchParams`,
   so faceted filter combinations create near-infinite crawlable URLs (crawl-budget
   waste + duplicate content) unless controlled.

---

## Design Decisions (confirmed with owner 2026-06-06)

| # | Decision | Choice | Rationale |
|---|---|---|---|
| D1 | **Site origin** | ✅ **Vercel** deploy; production domain **`https://watch.pandatrack.app`**, set via `NEXT_PUBLIC_SITE_URL`. Vercel injects `VERCEL_PROJECT_PRODUCTION_URL` / `VERCEL_URL` per environment — use those as fallbacks so preview deploys self-canonicalize. | Everything (sitemap/canonical/OG) needs one absolute origin; env var keeps prod/preview correct. |
| D2 | **Per-entity descriptions** | ✅ **Deterministic templates** from existing fields, computed in the data layer (no LLM) — author's call. Templates are the permanent baseline (free, idempotent, 100% coverage). An optional LLM enrichment pass that overwrites `description_es` for high-value items stays **deferred** (separate manually-invoked retrofit; respects the skills policy) — the templates remain the fallback, never the ceiling. | Best content-per-effort: ships full coverage now, leaves room to enrich the top of the catalog later without blocking SEO. |
| D3 | **i18n / hreflang** | ✅ **Spanish only for now** (`<html lang="es">`); hreflang **deferred**. Keep description/JSON-LD builders language-parameterizable (don't hard-code "es" deep in helpers) so localized routes are a later addition, not a rewrite. | UI is mono-language today; hreflang only pays off once true per-language URLs exist. Revisit if traction in other languages warrants it. |

> D1's final custom domain can be wired anytime via the env var; preview deploys work
> immediately off Vercel's injected URL. The rest of the work proceeds now.

---

## Functional Requirements

### FR-1: Absolute site URL helper
- Resolve the origin in order: `NEXT_PUBLIC_SITE_URL` → Vercel-injected
  `VERCEL_PROJECT_PRODUCTION_URL` / `VERCEL_URL` (scheme-less, prepend `https://`) →
  `http://localhost:3000` for dev. Preview deploys self-canonicalize this way.
- Expose `siteUrl()` and `absoluteUrl(path)` from `lib/seo.ts`.
- Document the (optional, until custom domain) env var in `.env.example`.

### FR-2: `robots`
- `app/robots.ts` (Next metadata route) returning:
  - `allow: /` for all user agents.
  - **Explicitly do not block LLM/AI crawlers** (GPTBot, ClaudeBot, anthropic-ai,
    PerplexityBot, Google-Extended, CCBot, etc.) — they are an intended discovery
    channel (per owner goal).
  - `disallow` for filtered/query catalog URLs (see FR-7) and any non-public path.
  - `sitemap:` pointing to the sitemap index (FR-3).

### FR-3: `sitemap`
- Generated from the data layer, reusing `allSeriesKeys()`, `allEditionKeys()`,
  `allSlugs()` (already exported from `lib/data.ts`).
- Entries: home `/`, every `/series/[seriesKey]`, `/edition/[editionKey]`, `/item/[slug]`.
- Each entry: absolute `url`, sensible `changeFrequency` / `priority`.
- **Single sitemap file.** Corpus is ~19k URLs (series + editions + items) — well under
  the 50,000-URL / 50 MB limit. Split per entity via `generateSitemaps()` only if/when it
  approaches that ceiling.

### FR-4: `manifest`
- `app/manifest.ts` with name, short_name, theme/background color, icons. Minimal PWA
  surface; improves mobile/installability signals.

### FR-5: Rich metadata per route (`generateMetadata`)
- Root layout: `title.template` (`%s · PandaWatch`), `metadataBase` (from FR-1),
  default description, `openGraph.siteName`, `locale`, Twitter card defaults,
  `applicationName`, theme color.
- **Home `/`**: add `generateMetadata` (currently missing) — keyword-oriented title +
  description ("ediciones especiales de manga: deluxe, box sets, limited, artbooks…").
- **`/series`, `/edition`, `/item`**: extend existing `generateMetadata` with:
  - `alternates.canonical` (absolute).
  - Full `openGraph` (`type`, `url`, `images[{url,width,height,alt}]`, `siteName`,
    `locale`); `/item` uses `og:type=product`.
  - `twitter` card (`summary_large_image`).
  - Description sourced from FR-6 (the entity description), not a bare count.

### FR-6: Per-entity descriptions (content)
- **`lib/descriptions.ts`** — deterministic template builders (D2):
  - `itemDescription(cluster)` → composed from `series_display`, `edition_display`,
    `volume`, `publisher`, `country`, `language`, `signal_types`, `extras[]`,
    `release_date`. Prefer the stored `description` / `description_es` when present;
    fall back to the template otherwise (never empty).
  - `editionDescription(clusters)` → aggregate (volume count, publisher, country,
    signal types, date range).
  - `seriesDescription(series)` → aggregate (edition count, item count, countries,
    publishers, top rarity).
- Used by both `generateMetadata` (FR-5) and rendered as **visible body text** on the
  page (search engines and LLMs index visible content, not just meta tags).

### FR-7: Crawl hygiene for filtered URLs
- Faceted/filtered catalog URLs (`/?filter=…`, `/?sort=…`, `/?page=…`) must not create
  indexable duplicates:
  - `robots.disallow` the query patterns (FR-2), **and/or**
  - emit `robots: { index: false, follow: true }` from the home `generateMetadata` when
    `searchParams` are present, with `alternates.canonical` pointing to the clean `/`.
- The clean catalog `/` and all detail pages remain fully indexable.

### FR-8: Structured data (JSON-LD)
- Injected as `<script type="application/ld+json">` per route (server-rendered):
  - **`/item`** → `Product` + `Book` (name, ISBN, author, publisher, datePublished,
    image, inLanguage) with an `Offer` (price, priceCurrency, availability derived from
    `rarity`/`stock_type`, seller from `sources[]`).
  - **`/edition`** → `CollectionPage` / `ItemList` linking its volumes.
  - **`/series`** → `CollectionPage` / `ItemList` linking its editions.
  - **All three** → `BreadcrumbList` (home → series → edition → item; the hierarchy
    already exists).
  - **Root layout** → `WebSite` (+ `SearchAction` for the sitelinks searchbox) and
    `Organization`.
- A small typed helper (`lib/jsonld.ts`) builds the objects; a `<JsonLd>` component
  serializes them safely.

### FR-9: Image alt-text strategy
- Cover images get descriptive `alt` derived from `series_display` + `edition_display` +
  `volume` (not the raw filename / generic "cover"). Centralize in the existing cover
  component.

---

## Non-Functional Requirements

- **No new runtime deps.** Use Next.js built-in metadata routes (`sitemap.ts`,
  `robots.ts`, `manifest.ts`, `generateMetadata`). No `next-seo`, no sitemap libs.
- **Server-rendered only.** All SEO surfaces emit at build/request time — never client JS.
- **Idempotent / data-driven.** Sitemap and descriptions derive entirely from
  `items.jsonl`; no hand-maintained lists.
- **Performance.** Cover LCP: `priority` on the hero image of detail pages; the rest lazy.
  Keep Core Web Vitals green.
- **Build cost.** Sitemap generation reuses the already-loaded clusters; no extra full
  passes over the corpus beyond what SSG already does.

---

## Out of Scope

- LLM-generated long-form descriptions (deferred — separate manual retrofit, D2).
- Per-language localized routes + hreflang (deferred, D3).
- Slug redirects / aliases (FRD-006 keeps slugs stable; out of scope here).
- Backlink building, off-page SEO, paid analytics.
- `web/index.html` (owner-only dashboard — never public, not indexed).

---

## Acceptance Criteria

- [ ] `NEXT_PUBLIC_SITE_URL` documented in `.env.example`; `lib/seo.ts` exports
      `siteUrl()` / `absoluteUrl()`.
- [ ] `/robots.txt` served, allows AI crawlers, disallows filter query params, references
      the sitemap.
- [ ] `/sitemap.xml` (index) lists home + all series/edition/item URLs as absolute URLs,
      segmented under the 50k limit.
- [ ] `/manifest.webmanifest` served with name + icons.
- [ ] Root layout sets `metadataBase`, `title.template`, OG site defaults, Twitter card.
- [ ] Home, series, edition, item pages all set canonical + full OG + Twitter + a real
      description (FR-6).
- [ ] Filtered home URLs are `noindex` / disallowed; clean `/` and detail pages indexable.
- [ ] JSON-LD validates in Google Rich Results Test for an item (Product/Book), an edition,
      a series (ItemList), and breadcrumbs on all.
- [ ] Cover images have descriptive alt text.
- [ ] `docs/web-next/README.md` index updated; SEO surfaces documented.

---

## Dependencies

- `lib/data.ts` — `allSeriesKeys()`, `allEditionKeys()`, `allSlugs()`,
  `clusterBySlug()`, `loadEditionClusters()`, `seriesByKey()` (all exist).
- `items.jsonl` fields — `slug`, `series_display`, `edition_display`, `publisher`,
  `country`, `language`, `isbn`, `author`, `release_date`, `rarity`,
  `stock_type`, `signal_types`, `extras[]`, `image_url`/`image_local`.
- Final production domain (D1) before go-live.
