import type { CSSProperties } from 'react'
import { cn } from '@/lib/styles'

type ScoreBadgeProps = {
  score: number
  showLabel?: boolean
  className?: string
}

// Maps raw scraper score (0–300) to design-system hex colors
function scoreStyle(score: number): CSSProperties {
  if (score >= 200) return {
    background: '#EDFAF3',
    color: '#1A8A5A',
    border: '2px solid #A6DFCA',
  }
  if (score >= 100) return {
    background: '#FFFBEB',
    color: '#9E6C00',
    border: '2px solid #FDE68A',
  }
  if (score >= 50) return {
    background: '#FEF3EF',
    color: '#D93D1A',
    border: '2px solid #FABEAD',
  }
  return {
    background: 'var(--ink-100)',
    color: 'var(--ink-500)',
    border: '2px solid var(--ink-200)',
  }
}

export function ScoreBadge({ score, showLabel = false, className }: ScoreBadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex flex-col items-center justify-center rounded-full',
        'w-10 h-10 text-xs font-bold leading-none tabular-nums',
        className,
      )}
      style={scoreStyle(score)}
      title={showLabel ? `Score: ${score}` : undefined}
    >
      {showLabel ? (
        <>
          <span className="text-[10px] font-medium opacity-70">Score</span>
          <span>{score}</span>
        </>
      ) : (
        score
      )}
    </span>
  )
}

export default ScoreBadge
