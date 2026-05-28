import type { HTMLAttributes } from 'react'
import { cn } from '@/lib/styles'

type HeadingSize = 'display' | 'h1' | 'h2' | 'h3' | 'h4'

const sizeClasses: Record<HeadingSize, string> = {
  display: 'text-5xl md:text-6xl font-bold leading-tight tracking-tight',
  h1: 'text-4xl font-bold leading-tight tracking-tight',
  h2: 'text-3xl font-bold leading-tight tracking-tight',
  h3: 'text-2xl font-bold leading-snug',
  h4: 'text-xl font-semibold leading-snug',
}

type HeadingProps = {
  as?: 'h1' | 'h2' | 'h3' | 'h4'
  size?: HeadingSize
  className?: string
  children: React.ReactNode
} & Omit<HTMLAttributes<HTMLHeadingElement>, 'color'>

export function Heading({ as: Element = 'h2', size, className, children, ...rest }: HeadingProps) {
  const effectiveSize = size ?? (Element as HeadingSize)
  return (
    <Element
      className={cn('text-text-primary', sizeClasses[effectiveSize], className)}
      {...rest}
    >
      {children}
    </Element>
  )
}

export default Heading
