import { Gift } from 'lucide-react'
import { formatDate } from '@/lib/format'
import type { ItemExtra } from '@/lib/types'

export function ExtrasSection({ extras }: { extras: ItemExtra[] }) {
  return (
    <section>
      <h2 style={{
        fontSize: 11, fontWeight: 600, textTransform: 'uppercase',
        letterSpacing: '0.08em', color: 'var(--color-text-secondary)',
        marginBottom: 12, marginTop: 0,
      }}>
        Incluye / Extras de primera edición
      </h2>
      <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
        {extras.map((extra, i) => (
          <li key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
            <Gift
              size={14}
              style={{ color: 'var(--bamboo-500)', flexShrink: 0, marginTop: 2 }}
            />
            <div>
              <span style={{ fontSize: 13, color: 'var(--color-text-primary)' }}>
                {extra.description_es || extra.description}
              </span>
              {extra.release_date && (
                <span style={{ fontSize: 12, color: 'var(--color-text-tertiary)', marginLeft: 6 }}>
                  {formatDate(extra.release_date)}
                </span>
              )}
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}

export default ExtrasSection
