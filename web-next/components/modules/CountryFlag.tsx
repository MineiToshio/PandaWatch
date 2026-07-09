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
    // Sin label visible, el país sigue existiendo para lectores de pantalla
    <span
      className={className ? `pw-country-flag ${className}` : 'pw-country-flag'}
      {...(!showLabel && { role: 'img', 'aria-label': country })}
    >
      <span aria-hidden="true">{flag}</span>
      {showLabel && (
        <span style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>
          {country}
        </span>
      )}
    </span>
  )
}

export default CountryFlag
