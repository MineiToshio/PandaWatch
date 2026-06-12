// El corpus trae release_date en 4 formatos reales: YYYY-MM-DD (ISO),
// YYYY-MM, YYYY (fechas parciales de fuentes de referencia) y DD/MM/YYYY
// (legacy de algunas fuentes ES). Cada granularidad se muestra con su propio
// nivel de detalle — parsear "2026" con new Date() lo corre a "31 dic 2025"
// en timezones negativas.
export function formatDate(dateStr: string): string {
  try {
    if (/^\d{4}$/.test(dateStr)) return dateStr

    if (/^\d{4}-\d{2}$/.test(dateStr)) {
      const d = new Date(dateStr + '-01T00:00:00')
      if (isNaN(d.getTime())) return dateStr
      return new Intl.DateTimeFormat('es-ES', { month: 'short', year: 'numeric' }).format(d)
    }

    const iso = toIsoDay(dateStr)
    if (iso) {
      const d = new Date(iso + 'T00:00:00')
      if (isNaN(d.getTime())) return dateStr
      return new Intl.DateTimeFormat('es-ES', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      }).format(d)
    }

    const d = new Date(dateStr)
    if (isNaN(d.getTime())) return dateStr
    return new Intl.DateTimeFormat('es-ES', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    }).format(d)
  } catch {
    return dateStr
  }
}

/** Día completo en ISO (YYYY-MM-DD), aceptando también DD/MM/YYYY. */
function toIsoDay(dateStr: string): string | null {
  if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) return dateStr
  const dmy = dateStr.match(/^(\d{2})\/(\d{2})\/(\d{4})$/)
  if (dmy) return `${dmy[3]}-${dmy[2]}-${dmy[1]}`
  return null
}

/**
 * Clave lexicográficamente ordenable para release_date. ISO y parciales
 * (YYYY, YYYY-MM) ya ordenan bien como string; DD/MM/YYYY se reordena a ISO
 * (sin esto, "31/10/2023" ordena como si fuera el item más reciente).
 */
export function sortableDate(dateStr: string): string {
  return toIsoDay(dateStr) ?? dateStr
}

export const PRODUCT_TYPE_LABELS: Record<string, string> = {
  manga:    'Manga',
  boxset:   'Cofre / Box Set',
  artbook:  'Artbook',
  fanbook:  'Fanbook',
  magazine: 'Revista',
  novel:    'Novela',
}

// --- Tipo de edición (badge) -----------------------------------------------
// El edition_key codifica {series}-{publisher}-{edition_slug}-{country}[-cNNNN].
// Desde la política de títulos 2026-06-12 el title es el nombre OFICIAL y ya
// no lleva el tipo de edición inyectado — el tipo se muestra como chip,
// derivado del edition_key (autoritativo post-standardize).
// Allowlist de países: mantener en sync con _VALID_COUNTRY de
// scripts/retrofit/fix_lmc_display_titles.py.
const EDITION_KEY_COUNTRIES = new Set([
  'es', 'it', 'fr', 'us', 'jp', 'mx', 'br', 'de', 'xx', 'vn', 'th', 'tw',
  'gb', 'kr', 'pt', 'ar', 'pe', 'cl', 'eslatam', 'latam',
])

export function editionSlugFromKey(editionKey?: string): string {
  if (!editionKey) return ''
  let parts = editionKey.split('-')
  // Sufijo -cNNNN: desambiguador de coleccion (gotcha #57)
  if (parts.length && /^c\d+$/.test(parts[parts.length - 1])) parts = parts.slice(0, -1)
  if (parts.length && EDITION_KEY_COUNTRIES.has(parts[parts.length - 1])) parts = parts.slice(0, -1)
  return parts.length >= 2 ? parts[parts.length - 1] : ''
}

/** Label en español del tipo de edición; null para regular/desconocido. */
export const EDITION_TYPE_LABELS: Record<string, string> = {
  special:     'Edición especial',
  limited:     'Edición limitada',
  collector:   'Coleccionista',
  deluxe:      'Deluxe',
  kanzenban:   'Kanzenban',
  perfect:     'Perfect',
  coffret:     'Coffret',
  boxset:      'Box Set',
  cofanetto:   'Cofanetto',
  variant:     'Variante',
  anniversary: 'Aniversario',
  celebration: 'Celebración',
  color:       'Color',
  maximum:     'Maximum',
  ultimate:    'Ultimate',
  master:      'Master',
  library:     'Library',
  integral:    'Integral',
  artbook:     'Artbook',
  fanbook:     'Fanbook',
  guidebook:   'Guidebook',
  magazine:    'Revista',
  steelbox:    'Steelbox',
  slipcase:    'Slipcase',
  prestige:    'Prestige',
  grimorio:    'Grimorio',
  grimoire:    'Grimoire',
  omnibus:     'Omnibus',
}

export function editionTypeLabel(editionKey?: string): string | null {
  const slug = editionSlugFromKey(editionKey)
  if (!slug || slug === 'regular') return null
  return EDITION_TYPE_LABELS[slug] ?? null
}
