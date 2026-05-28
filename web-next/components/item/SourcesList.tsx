import { ExternalLink } from 'lucide-react'
import { formatDate } from '@/lib/format'
import type { Item } from '@/lib/types'

function hostname(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, '') }
  catch { return url }
}

export function SourcesList({ items }: { items: Item[] }) {
  return (
    <section>
      <h2 style={{
        fontSize: 11, fontWeight: 600, textTransform: 'uppercase',
        letterSpacing: '0.08em', color: 'var(--color-text-secondary)',
        marginBottom: 12, marginTop: 0,
      }}>
        Fuentes ({items.length})
      </h2>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
              {['Fuente', 'Precio', 'Fecha', 'Stock'].map(h => (
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
            {items.map((item, i) => (
              <tr
                key={item.url}
                style={{ borderBottom: i < items.length - 1 ? '1px solid var(--color-border-subtle)' : 'none' }}
              >
                <td style={{ padding: '8px 16px 8px 0' }}>
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      display: 'inline-flex', alignItems: 'center', gap: 4,
                      color: 'var(--bamboo-500)', textDecoration: 'none',
                      fontSize: 13,
                    }}
                  >
                    {item.source || hostname(item.url)}
                    <ExternalLink size={11} style={{ flexShrink: 0 }} />
                  </a>
                </td>
                <td style={{ padding: '8px 16px 8px 0', color: 'var(--color-text-secondary)' }}>
                  {item.price ?? '—'}
                </td>
                <td style={{ padding: '8px 16px 8px 0', color: 'var(--color-text-secondary)', whiteSpace: 'nowrap' }}>
                  {item.release_date ? formatDate(item.release_date) : '—'}
                </td>
                <td style={{ padding: '8px 0', color: 'var(--color-text-secondary)' }}>
                  {item.stock_type ?? '—'}
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
