# BP-002: URL & Routing Schema

**Version:** 1.0  
**Status:** Draft  
**Author:** Architecture session 2026-05-27  
**Related FRDs:** FRD-003, FRD-004, FRD-005, FRD-006

---

## Purpose

Define the complete URL schema for PandaWatch App — all routes, their parameters,
and how they map to data. This is the source of truth for URL design decisions.

---

## Route Table

| Route | Next.js file | Type | Description |
|---|---|---|---|
| `/` | `app/page.tsx` | Server Component | Catalog — all editions, with filters |
| `/edition/[editionKey]` | `app/edition/[editionKey]/page.tsx` | Server Component (SSG) | All volumes of one edition |
| `/item/[slug]` | `app/item/[slug]/page.tsx` | Server Component (SSG) | Single item detail |

---

## URL Design Principles

1. **Flat over nested.** `/item/berserk-darkhorse-deluxe-42` instead of
   `/edition/berserk-darkhorse-deluxe/42`. One path segment per item.

2. **Human-readable slugs.** URLs should be recognizable without knowing the app:
   `pandawatch.local/item/berserk-darkhorse-deluxe-42` ✓
   `pandawatch.local/item/item-a3f9b12ce7d1` ← acceptable fallback only

3. **DB-migration-durable.** `edition_key` and `slug` are first-class fields in
   items.jsonl. In SQLite they become `TEXT UNIQUE` columns. URLs never change.

4. **Filter state = URL state.** No hidden client-side filter state. Every filtered
   view is a shareable URL.

5. **No hash routing.** The Alpine.js app used `#/edition/key` and `#/volume/url`.
   Hashes are not server-routable and not indexable. Real URL paths replace them.

---

## Route Details

### `/` — Catalog

```
URL: /?q=berserk&country=JP&signal_types=box_set&sort=date_desc&page=2

Params (all optional, all have defaults):
  q            string       Full-text search
  country      string[]     Filter by country (repeatable: &country=JP&country=FR)
  language     string[]     Filter by language
  publisher    string[]     Filter by publisher
  product_type string[]     Filter by product type
  source_class string[]     Filter by source class
  signal_types string[]     Filter by signal types (AND logic)
  min_score    number       Minimum score (default: 0)
  only_limited boolean      "true" to show only limited/special editions
  sort         string       Sort key (default: score_desc)
  page         number       Page number (default: 1)
```

**Shareable URLs:** Yes. All filter state in URL.

**Static generation:** No. The catalog is dynamically rendered per request
(many possible combinations of search params).

---

### `/edition/[editionKey]` — Edition Detail

```
URL: /edition/berserk-darkhorse-deluxe

Params:
  editionKey   string       Unique edition identifier (from edition_key field)

Optional query params:
  from         string       Referrer info for back-navigation (e.g., ?from=catalog)
```

**Examples:**
```
/edition/berserk-darkhorse-deluxe
/edition/one-piece-viz-collector
/edition/demon-slayer-shueisha-special
/edition/gon-norma-collector          ← box set (no volumes, 1 card)
/edition/nier-kurokawa-artbook
```

**Static generation:** Yes. `generateStaticParams()` runs at build time over
all distinct `edition_key` values.

**Not found:** If `editionKey` has no items in the corpus, returns 404.

---

### `/item/[slug]` — Item Detail

```
URL: /item/berserk-darkhorse-deluxe-42

Params:
  slug         string       Unique item identifier (from slug field in items.jsonl)

Optional query params:
  from         string       Referrer for back-navigation
                            "edition:{editionKey}" or "catalog"
```

**Slug format examples:**

| Item type | Example slug |
|---|---|
| Numbered volume with edition_key | `berserk-darkhorse-deluxe-42` |
| Numbered volume without edition_key* | `isbn-9781506721910` |
| Box set (no volume) | `gon-norma-collector` |
| Artbook (no volume) | `nier-kurokawa-artbook` |
| Standalone item (fallback) | `item-a3f9b12ce7d1` |

*Items without edition_key that have an ISBN use the ISBN-based slug.
Items with neither edition_key nor ISBN use the hash-based fallback.

**Static generation:** Yes. `generateStaticParams()` runs at build time over
all distinct `slug` values.

**Not found:** If `slug` has no matching item, returns 404.

---

## Navigation Flows

```
CATALOG (/)
    │
    │ click EditionCard (has edition_key)
    ▼
EDITION DETAIL (/edition/[editionKey])
    │
    │ click ItemCard
    ▼
ITEM DETAIL (/item/[slug])
    │
    │ ← back
    ▼
EDITION DETAIL (/edition/[editionKey])   ← via ?from=edition:{key}
    │
    │ ← back  
    ▼
CATALOG (/)                              ← preserves filter URL

CATALOG (/)
    │
    │ click EditionCard (no edition_key — standalone item)
    ▼
ITEM DETAIL (/item/[slug])               ← direct, skips edition level
    │
    │ ← back
    ▼
CATALOG (/)
```

---

## Back Navigation Implementation

The back navigation challenge: Server Components don't have access to the browser's
history stack. We solve this by encoding the referrer in the URL:

```tsx
// EditionCard.tsx (in catalog page)
<Link href={`/edition/${cluster.editionKey}?from=catalog`}>

// ItemCard.tsx (in edition page)
<Link href={`/item/${cluster.slug}?from=edition:${editionKey}`}>

// ItemDetail page — parse ?from to render correct back link
const from = searchParams.from
const backHref = from?.startsWith('edition:')
  ? `/edition/${from.slice(8)}`  // "edition:berserk-darkhorse-deluxe" → "/edition/..."
  : '/'
```

The catalog's filter state is NOT preserved in the back link (it would make URLs
very long). The user lands on `/` (unfiltered catalog) when navigating back from
an edition or item. This is acceptable for v1. Future: store filter state in
`sessionStorage` and restore on mount.

---

## Canonical URL Policy

Each item has exactly one canonical URL (`/item/[slug]`). The `edition_key` URL
(`/edition/[editionKey]`) is a collection view, not a canonical URL for any individual
item.

There are no redirect chains. All URLs are stable once assigned.

---

## Future Routes (not in scope for v1)

| Route | Description |
|---|---|
| `/series/[seriesKey]` | All editions of one series (Berserk across all publishers) |
| `/search` | Full-text search results page with query highlighting |
| `/new` | Recently added items (last 30 days) |
| `/api/feedback` | POST endpoint for 👎 button (when feedback moves to Next.js) |
