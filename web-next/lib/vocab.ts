/**
 * Vocabulario ÚNICO de señales (`signal_types`) y tipos de edición (slug del
 * `edition_key`). Antes repartido en 6 archivos — `KIND_RANK` (data.ts),
 * `EDITION_TYPE_LABELS` (format.ts), `SIGNALS_EQUIV_TO_EDITION` (EditionCard),
 * `SIGNAL_META` (SignalChip), `SIGNAL_ES` (descriptions.ts) y `LIMITED_SIGNALS`
 * (filters.ts) — con divergencias silenciosas (p.ej. `ultimate`/`integrale` en
 * KIND_RANK pero `integral` en EDITION_TYPE_LABELS; auditoría Fable 2026-07-08 #12).
 *
 * Una entrada cubre AMBOS espacios de claves porque varias señales y slugs de
 * tipo de edición son literalmente la misma cadena (`deluxe`, `kanzenban`,
 * `artbook`, `omnibus`, `limited`, `collector`). Dos flags gatean el uso por
 * contexto sin cambiar el comportamiento pre-existente de claves que NO
 * coincidían entre mapas:
 *   - `isEditionType`: la clave es un slug válido de `edition_key` → aparece
 *     como badge (`EditionTypeChip`/`editionTypeLabel`). Sin este flag, un
 *     slug con `rank` (usado sólo para desempatar tomos) no gana un badge que
 *     antes no tenía.
 *   - `isSignalType`: la clave es un `signal_type` real del corpus → cuenta
 *     para el fallback de `kindRank` (tier 3) y el filtro "sólo limitadas".
 *     Sin este flag, un slug de tipo de edición no se confunde con una señal.
 *
 * Fix intencional de la divergencia que el audit señaló: `integral` e
 * `integrale` (ES/FR) ahora comparten label + rank.
 */
import type { CSSProperties } from 'react'
import {
  Star, Sparkles, Package, Layers, BookOpen, Gem, Globe, Trophy,
  type LucideIcon,
} from 'lucide-react'

export type VocabEntry = {
  /** Label visible en español (chip de señal, badge de tipo de edición, prosa). */
  labelEs?: string
  /** Sólo señales con chip visual (SignalChip) llevan icon+bg+fg. */
  icon?: LucideIcon
  bg?: string
  fg?: string
  /** Orden de "prestigio" para desempatar tomos dentro de una edición (gotcha #60). Menor = antes. */
  rank?: number
  /** Sólo tipos de edición: signal_types redundantes con el badge (se omiten en la card). */
  equivSignals?: string[]
  /** Cuenta para el filtro "sólo ediciones limitadas / especiales". */
  isLimited?: boolean
  /** Clave válida como slug de edition_key → elegible para EditionTypeChip/editionTypeLabel. */
  isEditionType?: boolean
  /** Clave válida como signal_type real del corpus → elegible para SignalChip / kindRank tier 3. */
  isSignalType?: boolean
}

const NEUTRAL = { bg: '#EDE9E2', fg: '#706560' }

export const VOCAB: Record<string, VocabEntry> = {
  // ── Señales con chip visual (antes SIGNAL_META + SIGNAL_ES + LIMITED_SIGNALS) ──
  limited: {
    labelEs: 'Edición limitada', icon: Star, bg: '#FEF3EF', fg: '#D93D1A',
    rank: 2, isLimited: true, isEditionType: true, isSignalType: true,
    equivSignals: ['limited'],
  },
  special_edition: {
    labelEs: 'Edición especial', icon: Sparkles, bg: '#EDFAF3', fg: '#1A8A5A',
    rank: 2, isLimited: true, isSignalType: true,
  },
  collector: {
    labelEs: 'Coleccionista', icon: Trophy, bg: '#EDFAF3', fg: '#1A8A5A',
    rank: 2, isLimited: true, isEditionType: true, isSignalType: true,
    equivSignals: ['collector'],
  },
  box_set: {
    labelEs: 'Box Set', icon: Package, bg: '#EEF2FF', fg: '#2D52CC',
    rank: 5, isLimited: true, isSignalType: true,
  },
  variant_cover: {
    labelEs: 'Portada variante', icon: Layers, bg: '#FFFBEB', fg: '#9E6C00',
    rank: 1, isLimited: true, isSignalType: true,
  },
  artbook: {
    labelEs: 'Artbook', icon: BookOpen, bg: '#EEF2FF', fg: '#2D52CC',
    rank: 4, isLimited: true, isEditionType: true, isSignalType: true,
    equivSignals: ['artbook'],
  },
  deluxe: {
    labelEs: 'Deluxe', icon: Gem, bg: '#EEF2FF', fg: '#2D52CC',
    rank: 3, isLimited: true, isEditionType: true, isSignalType: true,
    equivSignals: ['deluxe'],
  },
  hardcover: {
    labelEs: 'Tapa dura', icon: BookOpen, ...NEUTRAL,
    rank: 3, isSignalType: true,
  },
  kanzenban: {
    labelEs: 'Kanzenban', icon: Layers, bg: '#EEF2FF', fg: '#2D52CC',
    rank: 3, isLimited: true, isEditionType: true, isSignalType: true,
    equivSignals: ['kanzenban'],
  },
  lore_edition: {
    labelEs: 'Lore Edition', icon: Sparkles, bg: '#EDFAF3', fg: '#1A8A5A',
    isLimited: true, isSignalType: true,
  },
  omnibus: {
    labelEs: 'Ómnibus', icon: BookOpen, ...NEUTRAL,
    rank: 3, isEditionType: true, isSignalType: true,
  },
  bonus: {
    labelEs: 'Con extras', icon: Package, bg: '#EDFAF3', fg: '#1A8A5A',
    isSignalType: true,
  },
  retailer_exclusive: {
    labelEs: 'Exclusiva de tienda', icon: Globe, bg: '#FFFBEB', fg: '#9E6C00',
    isLimited: true, isSignalType: true,
  },
  // Señales sin chip visual — sólo aportan rank al desempate de tomos
  // (kindRank tier 3); nunca tuvieron entrada en SIGNAL_META.
  premium_format: { rank: 2, isSignalType: true },
  bundle:         { rank: 5, isSignalType: true },

  // ── Sólo tipo de edición (antes EDITION_TYPE_LABELS / KIND_RANK) ──
  regular:     { rank: 0 }, // editionTypeLabel() nunca badgea "regular" (caso especial en la función)
  variant:     { labelEs: 'Variante', rank: 1, isEditionType: true, equivSignals: ['variant_cover'] },
  alternativa: { rank: 1 },
  special:     { labelEs: 'Edición especial', rank: 2, isEditionType: true, equivSignals: ['special_edition'] },
  especial:    { rank: 2 },
  limitada:    { rank: 2 },
  premium:     { rank: 2 },
  ultimate:    { labelEs: 'Ultimate', rank: 3, isEditionType: true },
  // Fix de la divergencia ES/FR (auditoría #12): antes sólo "integral" tenía
  // label y sólo "integrale" tenía rank — ahora ambas comparten los dos.
  integral:    { labelEs: 'Integral', rank: 3, isEditionType: true },
  integrale:   { labelEs: 'Integral', rank: 3, isEditionType: true },
  fanbook:     { labelEs: 'Fanbook', rank: 4, isEditionType: true },
  guidebook:   { labelEs: 'Guidebook', rank: 4, isEditionType: true },
  box:         { rank: 5 },
  boxset:      { labelEs: 'Box Set', rank: 5, isEditionType: true, equivSignals: ['box_set'] },
  coffret:     { labelEs: 'Coffret', rank: 5, isEditionType: true, equivSignals: ['box_set'] },
  cofanetto:   { labelEs: 'Cofanetto', isEditionType: true, equivSignals: ['box_set'] },
  perfect:     { labelEs: 'Perfect', isEditionType: true },
  anniversary: { labelEs: 'Aniversario', isEditionType: true },
  celebration: { labelEs: 'Celebración', isEditionType: true },
  color:       { labelEs: 'Color', isEditionType: true },
  maximum:     { labelEs: 'Maximum', isEditionType: true },
  master:      { labelEs: 'Master', isEditionType: true },
  library:     { labelEs: 'Library', isEditionType: true },
  magazine:    { labelEs: 'Revista', isEditionType: true },
  steelbox:    { labelEs: 'Steelbox', isEditionType: true },
  slipcase:    { labelEs: 'Slipcase', isEditionType: true },
  prestige:    { labelEs: 'Prestige', isEditionType: true },
  grimorio:    { labelEs: 'Grimorio', isEditionType: true },
  grimoire:    { labelEs: 'Grimoire', isEditionType: true },
}

/** signal_types que cuentan para el filtro "sólo ediciones limitadas / especiales" (filters.ts). */
export const LIMITED_SIGNAL_TYPES: ReadonlySet<string> = new Set(
  Object.entries(VOCAB).filter(([, v]) => v.isLimited).map(([k]) => k)
)

/** Rank de desempate de un slug de edition_key/cluster_key (tiers 1-2 de kindRank, data.ts). */
export function editionSlugRank(slug: string): number | undefined {
  return VOCAB[slug]?.rank
}

/** Rank de desempate mínimo entre los signal_types de un cluster (tier 3 de kindRank, data.ts). */
export function signalRank(signals: string[]): number | undefined {
  const ranks = signals
    .filter(s => VOCAB[s]?.isSignalType)
    .map(s => VOCAB[s]!.rank)
    .filter((r): r is number => r !== undefined)
  return ranks.length ? Math.min(...ranks) : undefined
}

/** Label del tipo de edición (badge), o null si el slug no es un tipo de edición reconocido. */
export function editionTypeLabelFromSlug(slug: string): string | null {
  const entry = VOCAB[slug]
  return entry?.isEditionType ? entry.labelEs ?? null : null
}

/** signal_types redundantes con el badge de tipo de edición de este slug (EditionCard). */
export function equivSignalsForSlug(slug: string): string[] {
  return VOCAB[slug]?.equivSignals ?? []
}

/** Meta de chip visual de una señal (SignalChip); null si no tiene representación visual. */
export function signalChipMeta(signal: string): { label: string; icon: LucideIcon; bg: string; fg: string } | null {
  const entry = VOCAB[signal]
  if (!entry?.icon || !entry.labelEs) return null
  return { label: entry.labelEs, icon: entry.icon, bg: entry.bg ?? NEUTRAL.bg, fg: entry.fg ?? NEUTRAL.fg }
}

/** Label en prosa (minúscula) de una señal para descriptions.ts; fallback determinístico. */
export function signalProseLabel(signal: string): string {
  return VOCAB[signal]?.labelEs?.toLowerCase() ?? signal.replace(/_/g, ' ')
}

export type { CSSProperties }
