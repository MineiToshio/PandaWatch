import type { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/styles'

type IconSize = 'xs' | 'sm' | 'md' | 'lg'

type IconProps = {
  icon: LucideIcon
  size?: IconSize
  className?: string
}

const sizeMap: Record<IconSize, number> = {
  xs: 12,
  sm: 16,
  md: 20,
  lg: 24,
}

export function Icon({ icon: LucideComponent, size = 'md', className }: IconProps) {
  return <LucideComponent size={sizeMap[size]} className={cn('shrink-0', className)} />
}

export default Icon
