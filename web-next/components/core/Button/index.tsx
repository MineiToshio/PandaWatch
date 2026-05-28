import type { ButtonHTMLAttributes, AnchorHTMLAttributes, ReactNode } from 'react'
import type { VariantProps } from 'class-variance-authority'
import { buttonVariants } from './buttonVariants'
import { cn } from '@/lib/styles'

type Variants = VariantProps<typeof buttonVariants>

export type ButtonProps = {
  variant?: Variants['variant']
  size?: Variants['size']
  children: ReactNode
  className?: string
} & Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'color'>

export type ButtonLinkProps = {
  variant?: Variants['variant']
  size?: Variants['size']
  children: ReactNode
  className?: string
  href: string
} & Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'color'>

export function Button({ variant, size, className, children, ...rest }: ButtonProps) {
  return (
    <button
      type="button"
      className={cn(buttonVariants({ variant, size }), className)}
      {...rest}
    >
      {children}
    </button>
  )
}

export function ButtonLink({ variant, size, className, children, href, ...rest }: ButtonLinkProps) {
  return (
    <a
      href={href}
      className={cn(buttonVariants({ variant, size }), className)}
      {...rest}
    >
      {children}
    </a>
  )
}

export { buttonVariants }
