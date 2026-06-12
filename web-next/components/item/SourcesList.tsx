import { ExternalLink } from 'lucide-react'
import { formatDate } from '@/lib/format'
import type { SourceEntry } from '@/lib/types'

function hostname(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, '') }
  catch { return url }
}

// Recibe el array `sources[]` guardado en la fila del producto (modelo
// 1-fila-por-producto). Cada entrada es una fuente: name/url/stock/fecha.
export function SourcesList({ sources }: { sources: SourceEntry[] }) {
  return (
    <section>
      <h2 style={{
        fontSize: 11, fontWeight: 600, textTransform: 'uppercase',
        letterSpacing: '0.08em', color: 'var(--color-text-secondary)',
        marginBottom: 12, marginTop: 0,
      }}>
        Fuentes ({sources.length})
      </h2>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
              {['Fuente', 'Fecha', 'Stock'].map(h => (
                <th key={h} style={{
                  textAlign: 'left', paddingBottom: 8, paddingRight: 16,
                  fontSize: 11, fontWeight: 500, color: 'var(--color-text-tertiary)',
                  whiteSpace: 'nowrap',
                }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sources.map((s, i) => (
              <tr
                key={s.url || i}
                style={{ borderBottom: i < sources.length - 1 ? '1px solid var(--color-border-subtle)' : 'none' }}
              >
                <td style={{ padding: '8px 16px 8px 0' }}>
                  <a
                    href={s.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      display: 'inline-flex', alignItems: 'center', gap: 4,
                      color: 'var(--bamboo-500)', textDecoration: 'none',
                      fontSize: 13,
                    }}
                  >
                    {s.name || hostname(s.url)}
                    <ExternalLink size={11} style={{ flexShrink: 0 }} />
                  </a>
                </td>
                <td style={{ padding: '8px 16px 8px 0', color: 'var(--color-text-secondary)', whiteSpace: 'nowrap' }}>
                  {s.release_date ? formatDate(s.release_date) : '—'}
                </td>
                <td style={{ padding: '8px 0', color: 'var(--color-text-secondary)' }}>
                  {s.stock_type || '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export default SourcesList
