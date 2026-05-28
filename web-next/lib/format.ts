export function formatDate(dateStr: string): string {
  try {
    // Date-only strings (YYYY-MM-DD) are parsed as UTC midnight by the Date constructor,
    // which shifts the day back one in negative-offset timezones. Appending T00:00:00
    // forces local-time parsing and keeps the correct calendar date.
    const normalized = /^\d{4}-\d{2}-\d{2}$/.test(dateStr) ? dateStr + 'T00:00:00' : dateStr
    return new Intl.DateTimeFormat('es-ES', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    }).format(new Date(normalized))
  } catch {
    return dateStr
  }
}

export function scoreLevel(score: number): 'green' | 'amber' | 'orange' | 'low' {
  if (score >= 200) return 'green'
  if (score >= 100) return 'amber'
  if (score >= 50)  return 'orange'
  return 'low'
}

export const PRODUCT_TYPE_LABELS: Record<string, string> = {
  manga:    'Manga',
  boxset:   'Cofre / Box Set',
  artbook:  'Artbook',
  fanbook:  'Fanbook',
  magazine: 'Revista',
  novel:    'Novela',
}
