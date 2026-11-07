import { CheckCircle2, Clock, Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export interface RunState {
  steps: string[]
  wait: string | null
  started: number
  // Les étapes attendues, pour montrer d'avance ce qui reste à faire.
  expected: string[]
}

export function ProgressPanel({ run, onCancel }: { run: RunState; onCancel: () => void }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 500)
    return () => window.clearInterval(timer)
  }, [])
  const seconds = Math.max(0, Math.round((now - run.started) / 1000))
  const upcoming = run.expected.filter((step) => !run.steps.includes(step))
  const current = run.steps.length - 1

  return (
    <div className="mx-auto flex w-full max-w-md flex-col gap-6 py-10" role="status" aria-live="polite">
      <div className="flex flex-col gap-1">
        <h2 className="text-lg font-semibold tracking-tight">Lecture de l'offre et de ton profil…</h2>
        <p className="flex items-center gap-1.5 text-[12.5px] text-muted-foreground tabular-nums">
          <Clock className="size-3.5" /> {seconds} s · en général 30 s à 1 min
        </p>
      </div>
      <ol className="flex flex-col gap-3">
        {run.steps.map((step, i) => (
          <li key={step} className="flex flex-col gap-1">
            <span className={cn('flex items-center gap-2 text-[13px]', i < current && 'text-muted-foreground')}>
              {i < current ? (
                <CheckCircle2 className="size-4 text-success" />
              ) : (
                <Loader2 className="size-4 animate-spin text-primary" />
              )}
              {step}
            </span>
            {i === current && run.wait && <span className="ml-6 text-[12px] text-warning">{run.wait}</span>}
          </li>
        ))}
        {upcoming.map((step) => (
          <li key={step} className="flex items-center gap-2 text-[13px] text-muted-foreground/60">
            <span className="flex size-4 items-center justify-center">
              <span className="size-1.5 rounded-full bg-muted-foreground/40" />
            </span>
            {step}
          </li>
        ))}
      </ol>
      <Button variant="outline" size="sm" className="w-fit" onClick={onCancel}>
        Annuler
      </Button>
    </div>
  )
}
