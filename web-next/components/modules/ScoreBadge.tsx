import type { CSSProperties } from 'react'
import { cn } from '@/lib/styles'
import { scoreLevel } from '@/lib/format'

type ScoreBadgeProps = {
  score: number
  showLabel?: boolean
  className?: string
}

const SCORE_STYLES: Record<ReturnType<typeof scoreLevel>, CSSProperties> = {
  green:  { background: '#EDFAF3', color: '#1A8A5A', border: '2px solid #A6DFCA' },
  amber:  { background: '#FFFBEB', color: '#9E6C00', border: '2px solid #FDE68A' },
  orange: { background: '#FEF3EF', color: '#D93D1A', border: '2px solid #FABEAD' },
  low:    { background: 'var(--ink-100)', color: 'var(--ink-500)', border: '2px solid var(--ink-200)' },
}

function scoreStyle(score: number): CSSProperties {
  return SCORE_STYLES[scoreLevel(score)]
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
