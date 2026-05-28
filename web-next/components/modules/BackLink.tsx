import Link from 'next/link'
import { ChevronLeft } from 'lucide-react'

type BackLinkProps = {
  href: string
  label: string
}

export function BackLink({ href, label }: BackLinkProps) {
  return (
    <Link
      href={href}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        fontSize: 14,
        color: 'var(--color-text-secondary)',
        textDecoration: 'none',
        marginBottom: 24,
        transition: 'color var(--duration-fast)',
      }}
    >
      <ChevronLeft size={16} strokeWidth={2} aria-hidden="true" />
      {label}
    </Link>
  )
}

export default BackLink
