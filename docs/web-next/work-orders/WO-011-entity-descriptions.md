# WO-011: Per-entity Descriptions (template content)

**Phase:** 5
**Effort:** M
**Status:** Complete (2026-06-06)
**Related:** [FRD-008](../FRD-008-seo-discoverability.md) FR-6 (Decision D2)
**Prerequisites:** WO-003 (data layer / types)

---

## Objective

Give every series, edition, and item real, indexable text — deterministically composed
from existing fields, no LLM (FRD-008 D2). Used both as the meta `description` (WO-010)
and as **visible body copy** on the page (search engines and LLMs index rendered text).
This is what turns thin image+price pages into rankable, citable content.

---

## Tasks

### Task 1: `lib/descriptions.ts`

Pure functions, no I/O. Prefer stored prose, fall back to a template, never return empty.

```ts
import type { Cluster, Series } from '@/lib/types'

const SIGNAL_ES: Record<string, string> = {
  box_set: 'box set', limited: 'edición limitada', deluxe_edition: 'edición deluxe',
  special_edition: 'edición especial', variant_cover: 'portada variante',
  artbook: 'artbook', slipcase: 'estuche', kanzenban: 'kanzenban', /* … */
}

export function itemDescription(cluster: Cluster): string {
  const c = cluster.canonical
  if (c.description_es?.trim()) return c.description_es.trim()
  if (c.description?.trim()) return c.description.trim()

  const series = cluster.seriesDisplay ?? c.title
  const edition = cluster.editionDisplay ? ` ${cluster.editionDisplay}` : ''
  const vol = c.volume ? `, Vol. ${c.volume}` : ''
  const kinds = cluster.signalTypes.map(s => SIGNAL_ES[s] ?? s).slice(0, 3).join(', ')
  const where = [c.publisher, c.country].filter(Boolean).join(' · ')
  const lang = c.language ? ` en ${c.language}` : ''
  const extras = (c.extras ?? []).map(e => e.description).filter(Boolean).slice(0, 2)

  let s = `${series}${edition}${vol} — ${kinds || 'edición física'}${lang}`
  if (where) s += ` publicada por ${where}`
  s += '.'
  if (extras.length) s += ` Incluye ${extras.join('; ')}.`
  if (c.release_date) s += ` Fecha de lanzamiento: ${c.release_date}.`
  return s
}

export function editionDescription(clusters: Cluster[]): string {
  const c = clusters[0].canonical
  const n = clusters.length
  const kinds = [...new Set(clusters.flatMap(x => x.signalTypes))].map(s => SIGNAL_ES[s] ?? s).slice(0, 3).join(', ')
  return `${clusters[0].editionDisplay ?? clusters[0].seriesDisplay}: ${n} ${n === 1 ? 'tomo' : 'tomos'}`
    + ` de ${[c.publisher, c.country].filter(Boolean).join(' · ')}`
    + (kinds ? ` — ${kinds}.` : '.')
}

export function seriesDescription(series: Series): string {
  const places = series.countries.join(', ')
  const pubs = series.publishers.slice(0, 3).join(', ')
  return `${series.seriesDisplay}: ${series.editionCount} ediciones especiales`
    + ` (${series.itemCount} tomos) de ${pubs}`
    + (places ? `, disponibles en ${places}.` : '.')
}
```
> Keep the Spanish copy natural; expand `SIGNAL_ES` to cover all `signal_types` in use
> (cross-check `docs/reference/` for the canonical list).

### Task 2: Render descriptions as visible content

- **Item** (`ItemHero` / item page): render `itemDescription(cluster)` in a `<p>` near
  the title (not visually hidden — must be real on-page text).
- **Edition** (`EditionHeader`): render `editionDescription(clusters)` as a lede paragraph.
- **Series** (`SeriesHeader`): render `seriesDescription(series)` as a lede paragraph.

### Task 3: Wire into metadata

Confirm WO-010's `generateMetadata` imports these (item/edition/series). Single source of
truth — meta description and visible text match.

### Task 4 (optional, deferred — DO NOT auto-run)

Document a future `scripts/retrofit/enrich_descriptions.py` (manual, LLM-backed) that
writes richer unique `description_es` into `items.jsonl` for high-value items. Out of
scope for this WO; noted so the template functions remain the fallback, not the ceiling.
Respects the skills/no-auto-run policy in CLAUDE.md.

---

## Files Created/Modified

- `web-next/lib/descriptions.ts` (new)
- `web-next/components/item/ItemHero.tsx` (render description)
- `web-next/components/edition/EditionHeader.tsx`
- `web-next/components/series/SeriesHeader.tsx`

---

## Acceptance Criteria

- [x] Every item/edition/series renders a non-empty description in the page HTML.
- [x] Stored `description_es` / `description` is preferred when present (verified: item
      `…madoka-magica-rebellion-meian-coffret` renders its stored prose); template fills the rest.
- [x] Output is natural Spanish, no leftover keys (`box_set` → "box set", etc.).
- [x] Rendered on series (`/series/one-piece`), edition, and item routes.
- [x] `tsc --noEmit` clean; `lib/descriptions.ts` is pure (no client-only code).
- [ ] Wire into `generateMetadata` — done in WO-010 (meta description = on-page text).

---

## Verification

`preview_snapshot` on an item, an edition, and a series page; confirm the description
paragraph is present in the accessibility tree (real text, indexable).
