import { Check, Loader2, RefreshCw } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import type { CloneResult } from '@/lib/types'
import { cn } from '@/lib/utils'

export type CloneState = { status: 'idle' } | { status: 'running' } | { status: 'done'; result: CloneResult; version: number } | { status: 'error'; message: string }

const BADGE: Record<string, string> = {
  identique: 'bg-status-offer-soft text-status-offer',
  'mêmes largeurs': 'bg-status-sent-soft text-status-sent',
  proche: 'bg-status-interview-soft text-status-interview',
}

/** Le clone : la note de ressemblance, ton PDF et le clone superposés, ce qui est repris ou non. */
export function ClonePanel({ id, state, retry, Pdf }: { id: string; state: CloneState; retry: () => void; Pdf: (props: { url: string }) => React.ReactNode }) {
  const [split, setSplit] = useState(50)
  if (state.status === 'idle' || state.status === 'running') {
    return (
      <div role="status" className="flex flex-col items-center justify-center gap-2 rounded-xl border bg-card surface py-20 text-center text-[13px] text-muted-foreground">
        <Loader2 className="size-5 animate-spin" />
        <span>Clonage de la forme de ton PDF…</span>
        <span className="text-[12px]">L'appli compile le clone, le compare à ton PDF et corrige les écarts (15 à 30 secondes).</span>
      </div>
    )
  }
  if (state.status === 'error') {
    return (
      <div className="flex flex-col items-start gap-3 rounded-xl border bg-card surface p-5 text-[13px]">
        <p className="text-muted-foreground">{state.message}</p>
        <Button size="sm" variant="outline" className="gap-1.5" onClick={retry}>
          <RefreshCw className="size-3.5" /> Réessayer
        </Button>
      </div>
    )
  }
  const { result, version } = state
  if (!result.available || !result.ok) {
    return (
      <p role="note" className="rounded-xl border bg-card surface p-5 text-[13px] text-muted-foreground">
        {result.reason ?? 'Le clone n’est pas possible pour ce PDF.'} Choisis « Proche du mien » ou « Style de l'appli ».
      </p>
    )
  }
  const tone = (result.likeness ?? 0) >= 90 ? 'text-status-offer bg-status-offer-soft' : (result.likeness ?? 0) >= 75 ? 'text-status-sent bg-status-sent-soft' : 'text-status-interview bg-status-interview-soft'
  return (
    <div className="flex flex-wrap items-start gap-5">
      <div className="flex min-w-0 flex-[1_1_300px] flex-col gap-2 sm:max-w-[380px]">
        <div className="flex justify-between text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
          <span>Ton PDF</span>
          <span>Le clone</span>
        </div>
        <div className="relative" aria-label="Ton PDF et le clone superposés">
          <Pdf url={api.importSourceUrl(id)} />
          <div className="absolute inset-0" style={{ clipPath: `inset(0 0 0 ${split}%)` }}>
            <Pdf url={api.importCloneUrl(id, version)} />
          </div>
          <span aria-hidden className="pointer-events-none absolute -top-1.5 -bottom-1.5 w-0.5 -translate-x-1/2 bg-primary shadow-[0_0_0_3px] shadow-primary/25" style={{ left: `${split}%` }} />
        </div>
        <input type="range" min={0} max={100} value={split} onChange={(e) => setSplit(Number(e.target.value))} aria-label="Part du clone affichée" className="w-full accent-[var(--primary)]" />
        <span className="text-[12px] text-muted-foreground">Glisse pour passer de ton PDF au clone.</span>
      </div>
      <div className="flex min-w-0 flex-[999_1_260px] flex-col gap-4">
        <div className={cn('flex flex-col gap-1 rounded-xl px-4 py-3', tone)}>
          <span className="text-[12px] font-medium">Ressemblance avec ton PDF</span>
          <span className="font-mono text-[24px] font-semibold tabular-nums" aria-label={`Ressemblance : ${result.likeness} sur 100`}>
            {result.likeness} %
          </span>
          <span className="text-[12px] opacity-90">Mesurée en superposant les deux pages : place de chaque mot, couleurs, formes.</span>
        </div>
        <div className="flex flex-col gap-1.5">
          <span className="text-[11px] font-bold tracking-wider text-muted-foreground uppercase">Repris à l'identique</span>
          <ul className="flex flex-col gap-1 text-[13px]">
            {result.kept.map((line) => (
              <li key={line} className="flex gap-1.5">
                <Check className="mt-0.5 size-3.5 shrink-0 text-status-offer" /> {line}
              </li>
            ))}
          </ul>
        </div>
        <div className="flex flex-col gap-1.5">
          <span className="text-[11px] font-bold tracking-wider text-muted-foreground uppercase">Polices</span>
          <ul className="flex flex-col gap-1 text-[13px]">
            {result.fonts.map((font) => (
              <li key={font.pdf} className="flex flex-wrap items-center gap-1.5">
                <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-semibold', BADGE[font.badge] ?? BADGE.proche)}>{font.badge}</span>
                {font.pdf === font.name.replace(/\s/g, '') ? font.name : `${font.pdf} → ${font.name}`}
              </li>
            ))}
          </ul>
        </div>
        {result.differences.length > 0 && (
          <div className="flex flex-col gap-1.5">
            <span className="text-[11px] font-bold tracking-wider text-muted-foreground uppercase">Pas tout à fait identique</span>
            <ul className="flex list-disc flex-col gap-1 pl-4 text-[13px] text-foreground/85">
              {result.differences.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}
