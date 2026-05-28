import { cn } from '@/lib/styles'

const COUNTRY_FLAGS: Record<string, string> = {
  // Spanish names (as stored in items.jsonl)
  'Japón':          '🇯🇵',
  'España':         '🇪🇸',
  'Francia':        '🇫🇷',
  'Italia':         '🇮🇹',
  'Alemania':       '🇩🇪',
  'Brasil':         '🇧🇷',
  'México':         '🇲🇽',
  'Argentina':      '🇦🇷',
  'Vietnam':        '🇻🇳',
  'Tailandia':      '🇹🇭',
  'Taiwán':         '🇹🇼',
  'Estados Unidos': '🇺🇸',
  'Canadá':         '🇨🇦',
  // English / native names (for showcase page and future use)
  'Japan':          '🇯🇵',
  'France':         '🇫🇷',
  'Italy':          '🇮🇹',
  'Germany':        '🇩🇪',
  'Brazil':         '🇧🇷',
  'Thailand':       '🇹🇭',
  'Taiwan':         '🇹🇼',
  'United States':  '🇺🇸',
  'Canada':         '🇨🇦',
}

type CountryFlagProps = {
  country: string
  showLabel?: boolean
  className?: string
}

export function CountryFlag({ country, showLabel = false, className }: CountryFlagProps) {
  const flag = COUNTRY_FLAGS[country] ?? '🌐'

  return (
    <span className={cn('inline-flex items-center gap-1', className)}>
      <span aria-hidden="true">{flag}</span>
      {showLabel && (
        <span className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
          {country}
        </span>
      )}
    </span>
  )
}

export default CountryFlag
