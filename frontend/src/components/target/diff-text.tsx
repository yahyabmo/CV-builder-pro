import { useMemo } from 'react'

import { wordDiff } from '@/lib/diff'
import { cn } from '@/lib/utils'

/** Ancien et nouveau texte fondus : retiré barré, ajouté surligné. */
export function DiffText({ before, after, className }: { before: string; after: string; className?: string }) {
  const pieces = useMemo(() => wordDiff(before, after), [before, after])
  return (
    <p className={cn('text-[13px] leading-relaxed whitespace-pre-wrap', className)}>
      {pieces.map((piece, i) =>
        piece.kind === 'same' ? (
          <span key={i}>{piece.text}</span>
        ) : piece.kind === 'removed' ? (
          <del key={i} className="rounded-sm bg-destructive/10 text-destructive/80 decoration-destructive/50">
            {piece.text}
          </del>
        ) : (
          <ins key={i} className={cn('rounded-sm bg-success/15 text-foreground no-underline', pieces[i - 1]?.kind === 'removed' && 'ml-0.5')}>
            {piece.text}
          </ins>
        ),
      )}
    </p>
  )
}
