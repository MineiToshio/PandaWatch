import type { HTMLAttributes } from 'react'
import { cn } from '@/lib/styles'

type TypographyVariant = 'body' | 'body-sm' | 'caption' | 'eyebrow'

const variantClasses: Record<TypographyVariant, string> = {
  'body': 'text-base leading-relaxed',
  'body-sm': 'text-sm leading-relaxed',
  'caption': 'text-xs leading-normal',
  'eyebrow': 'text-xs uppercase tracking-widest font-medium',
}

type TypographyProps = {
  variant?: TypographyVariant
  as?: 'p' | 'span' | 'div' | 'label'
  className?: string
  children: React.ReactNode
} & Omit<HTMLAttributes<HTMLElement>, 'color'>

export function Typography({
  variant = 'body',
  as: Element = 'p',
  className,
  children,
  ...rest
}: TypographyProps) {
  return (
    <Element
      className={cn(variantClasses[variant], className)}
      {...rest}
    >
      {children}
    </Element>
  )
}

export default Typography
