import { cva } from 'class-variance-authority'

// Button spec sourced from preview/components-states.html (Clear-all / Show-results /
// Try-again actions) and components-header.html (filter-btn). Sizes match the design
// system's CTA scale: sm = 32px (chip-actions), md = 38px (primary CTA), lg = 44px.
// Font is Space Grotesk weight 600 for primary CTAs, 13–14px depending on size.
export const buttonVariants = cva(
  [
    'relative inline-flex items-center justify-center gap-2',
    'rounded-[8px] cursor-pointer select-none whitespace-nowrap',
    "font-semibold [font-family:var(--font-display)]",
    'transition-[background-color,color,border-color,box-shadow,transform,opacity]',
    'duration-[var(--duration-fast)]',
    'focus-visible:outline-2 focus-visible:outline-offset-2',
    'focus-visible:[outline-color:var(--bamboo-500)]',
    '[&:focus-visible]:[box-shadow:0_0_0_3px_var(--color-focus-ring)]',
    'disabled:pointer-events-none disabled:opacity-50',
  ],
  {
    variants: {
      variant: {
        primary: [
          '[background:var(--color-primary)] text-white border border-transparent [box-shadow:var(--shadow-sm)]',
          'hover:[background:var(--color-primary-hover)] hover:-translate-y-px hover:[box-shadow:var(--shadow-md)]',
          'active:translate-y-0 active:[box-shadow:var(--shadow-sm)] active:[background:var(--color-primary-active)]',
        ],
        secondary: [
          'bg-white [color:var(--color-text-primary)] border [border-color:var(--color-border)]',
          'hover:[background:var(--ink-50)] hover:-translate-y-px hover:[box-shadow:var(--shadow-sm)]',
          'active:translate-y-0',
        ],
        ghost: [
          'bg-transparent [color:var(--color-text-primary)] border [border-color:var(--color-border)]',
          'hover:[background:var(--ink-100)] hover:-translate-y-px',
          'active:translate-y-0',
        ],
        outline: [
          'bg-white [color:var(--color-primary)] [border-color:var(--bamboo-200)] border',
          'hover:[background:var(--color-primary-subtle)] hover:-translate-y-px hover:[box-shadow:var(--shadow-sm)]',
          'active:translate-y-0',
        ],
        link: [
          '[color:var(--color-primary)] bg-transparent border-0 shadow-none p-0 h-auto',
          'hover:underline underline-offset-4 hover:[color:var(--color-primary-hover)]',
        ],
        tonal: [
          '[background:var(--color-primary-tint)] [color:var(--color-primary)]',
          'hover:[background:var(--bamboo-200)] hover:-translate-y-px',
          'active:translate-y-0',
          'border border-transparent',
        ],
        destructive: [
          '[background:var(--color-secondary)] text-white border border-transparent [box-shadow:var(--shadow-sm)]',
          'hover:[background:var(--color-secondary-hover)] hover:-translate-y-px hover:[box-shadow:var(--shadow-md)]',
          'active:translate-y-0 active:[box-shadow:var(--shadow-sm)]',
        ],
      },
      size: {
        sm: 'h-8 px-3 text-[12px]',
        md: 'h-[38px] px-4 text-[13px]',
        lg: 'h-11 px-5 text-[14px]',
      },
    },
    defaultVariants: {
      variant: 'primary',
      size: 'md',
    },
  },
)
