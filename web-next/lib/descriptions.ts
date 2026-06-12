/**
 * Per-entity descriptions (FRD-008 FR-6, Decision D2).
 *
 * Deterministic Spanish prose composed from existing fields — no LLM. Used both as the
 * meta `description` (generateMetadata) and as visible on-page body text. Stored
 * `description_es` / `description` is always preferred; the template is the fallback so
 * a description is NEVER empty.
 *
 * Keep these language-parameterizable in spirit (D3): Spanish-only today, but the copy
 * lives here so localized variants are a later addition, not a rewrite.
 */
import type { Cluster, Series } from '@/lib/types'

/** Spanish labels for signal_types. Mirrors the vocabulary in SignalChip.tsx. */
const SIGNAL_ES: Record<string, string> = {
  limited: 'edición limitada',
  special_edition: 'edición especial',
  collector: 'edición de coleccionista',
  box_set: 'box set',
  variant_cover: 'portada variante',
  artbook: 'artbook',
  deluxe: 'edición deluxe',
  hardcover: 'tapa dura',
  kanzenban: 'kanzenban',
  lore_edition: 'lore edition',
  omnibus: 'ómnibus',
  bonus: 'con extras',
  retailer_exclusive: 'exclusiva de tienda',
}

function signalsToEs(signals: string[], limit = 3): string {
  return signals
    .map(s => SIGNAL_ES[s] ?? s.replace(/_/g, ' '))
    .slice(0, limit)
    .join(', ')
}

/**
 * Strip "read more" boilerplate that some sources leak into the description field
 * (e.g. "MÁS INFORMACIÓN …", "EN SAVOIR PLUS …"). Defensive only — the real fix is
 * upstream data cleaning; this keeps the meta description + on-page text clean meanwhile.
 */
const READ_MORE_PREFIX =
  /^\s*(M[ÁA]S INFORMACI[ÓO]N|EN SAVOIR PLUS|LEER M[ÁA]S|VER M[ÁA]S|READ MORE|MEHR ERFAHREN|SCOPRI DI PI[ÙU])\s*[:.-]?\s*/i

function clean(text: string): string {
  return text.replace(READ_MORE_PREFIX, '').trim()
}

/**
 * Item description. Prefers stored prose, falls back to a composed template.
 */
export function itemDescription(cluster: Cluster): string {
  const c = cluster.canonical
  const stored = clean(c.description_es?.trim() || c.description?.trim() || '')
  if (stored) return stored

  const series = cluster.seriesDisplay ?? c.series_display ?? c.title
  const edition = cluster.editionDisplay ? ` ${cluster.editionDisplay}` : ''
  const vol = c.volume ? `, Vol. ${c.volume}` : ''
  const kinds = signalsToEs(cluster.signalTypes)
  const where = [c.publisher, c.country].filter(Boolean).join(' · ')
  const lang = c.language ? ` en ${c.language}` : ''
  const extras = (c.extras ?? [])
    .map(e => (e.description_es?.trim() || e.description?.trim()))
    .filter(Boolean)
    .slice(0, 2) as string[]

  let s = `${series}${edition}${vol} — ${kinds || 'edición física especial'}${lang}`
  if (where) s += ` publicada por ${where}`
  s += '.'
  if (extras.length) s += ` Incluye ${extras.join('; ')}.`
  return s
}

/**
 * Edition description — aggregate over its volumes.
 * `signalTypes` is the edition-level aggregate (as passed to EditionHeader); falls back
 * to the representative cluster's own signals.
 */
export function editionDescription(
  cluster: Cluster,
  totalVolumes: number,
  signalTypes?: string[],
): string {
  const c = cluster.canonical
  const name = cluster.editionDisplay ?? cluster.seriesDisplay ?? c.title
  const where = [c.publisher, c.country].filter(Boolean).join(' · ')
  const kinds = signalsToEs(signalTypes ?? cluster.signalTypes)
  const tomos = `${totalVolumes} ${totalVolumes === 1 ? 'tomo' : 'tomos'}`

  let s = `${name}: ${tomos}`
  if (where) s += ` de ${where}`
  s += kinds ? ` — ${kinds}.` : '.'
  if (c.language) s += ` Edición en ${c.language}.`
  return s
}

/**
 * Series description — aggregate over its editions.
 */
export function seriesDescription(series: Series): string {
  const edLabel = series.editionCount === 1 ? 'edición especial' : 'ediciones especiales'
  const tomoLabel = series.itemCount === 1 ? 'tomo' : 'tomos'
  const pubs = series.publishers.slice(0, 3).join(', ')
  const places = series.countries.slice(0, 5).join(', ')

  let s = `${series.seriesDisplay}: ${series.editionCount} ${edLabel} (${series.itemCount} ${tomoLabel})`
  if (pubs) s += ` de ${pubs}`
  s += '.'
  if (places) s += ` Disponibles en ${places}.`
  return s
}
