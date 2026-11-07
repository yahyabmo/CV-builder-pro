import { ArrowRight } from 'lucide-react'

import type { Coverage, Keyword } from '@/lib/types'
import { cn } from '@/lib/utils'

function tone(score: number) {
  return score >= 70 ? 'text-success' : score >= 45 ? 'text-warning' : 'text-destructive'
}

/** Le score de couverture (avant → après si les deux sont donnés). */
export function ScoreLine({ after, before, caption }: { after: number; before?: number; caption: string }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline gap-2">
        {before != null && (
          <>
            <span className="text-[15px] font-medium text-muted-foreground tabular-nums">{before}</span>
            <ArrowRight className="size-3.5 self-center text-muted-foreground" />
          </>
        )}
        <span className={cn('text-3xl font-semibold tracking-tight tabular-nums', tone(after))}>{after}</span>
        <span className="text-[12px] text-muted-foreground">/ 100</span>
      </div>
      <div className="relative h-1.5 overflow-hidden rounded-full bg-muted">
        {before != null && <div className="absolute inset-y-0 left-0 bg-foreground/15" style={{ width: `${before}%` }} />}
        <div
          className={cn('absolute inset-y-0 left-0 rounded-full transition-[width] duration-500', after >= 70 ? 'bg-success' : after >= 45 ? 'bg-warning' : 'bg-destructive')}
          style={{ width: `${after}%`, opacity: before != null ? 0.85 : 1 }}
        />
      </div>
      <p className="text-[11px] text-muted-foreground">{caption}</p>
    </div>
  )
}

/** Les mots-clés de l'offre, présents puis absents, avec leur importance. */
export function KeywordChips({ coverage, keywords }: { coverage: Coverage; keywords: Keyword[] }) {
  const weight = new Map(keywords.map((k) => [k.term, k.importance]))
  const chip = (term: string, present: boolean) => (
    <span
      key={term}
      title={`Importance ${weight.get(term) ?? 1} sur 3`}
      className={cn(
        'inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px]',
        present ? 'border-success/30 bg-success/10 text-foreground' : 'border-dashed text-muted-foreground',
      )}
    >
      {term}
      <span className="flex gap-px" aria-hidden>
        {[1, 2, 3].slice(0, weight.get(term) ?? 1).map((n) => (
          <span key={n} className={cn('size-1 rounded-full', present ? 'bg-success' : 'bg-muted-foreground/50')} />
        ))}
      </span>
    </span>
  )
  return (
    <div className="flex flex-col gap-2.5">
      {coverage.present.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <p className="text-[11px] font-medium text-muted-foreground">Dans le CV ({coverage.present.length})</p>
          <div className="flex flex-wrap gap-1">{coverage.present.map((t) => chip(t, true))}</div>
        </div>
      )}
      {coverage.absent.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <p className="text-[11px] font-medium text-muted-foreground">Absents ({coverage.absent.length})</p>
          <div className="flex flex-wrap gap-1">{coverage.absent.map((t) => chip(t, false))}</div>
        </div>
      )}
    </div>
  )
}
