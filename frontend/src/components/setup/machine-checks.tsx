import { CheckCircle2, Copy, Loader2, MinusCircle, RefreshCw, TriangleAlert } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import type { Machine, MachineCheck } from '@/lib/types'
import { cn } from '@/lib/utils'

export function RecheckButton({ busy, onClick }: { busy: boolean; onClick: () => void }) {
  return (
    <Button variant="outline" size="sm" onClick={onClick} disabled={busy} className="gap-1.5">
      {busy ? <Loader2 className="size-3.5 animate-spin" /> : <RefreshCw className="size-3.5" />} Vérifier à nouveau
    </Button>
  )
}

const copy = async (text: string) => {
  try {
    await navigator.clipboard.writeText(text)
    toast.success('Commande copiée', { description: 'Colle-la dans un terminal.' })
  } catch {
    toast.error('Copie impossible', { description: 'Sélectionne la commande et copie-la à la main.' })
  }
}

function Row({ check, system, last }: { check: MachineCheck; system: Machine['system']; last: boolean }) {
  if (check.ok === false) {
    return (
      <li className={cn('flex flex-col gap-3 bg-status-interview-soft/45 px-5 py-4', !last && 'border-b')}>
        <div className="flex flex-wrap items-center gap-x-3.5 gap-y-1.5">
          <TriangleAlert className="size-4.5 text-status-interview" aria-hidden="true" />
          <span className="flex-[1_1_200px] font-semibold">
            {check.label} : {check.detail}
          </span>
          <span className="rounded-full bg-status-interview-soft px-2.5 py-0.5 text-[11.5px] font-semibold text-status-interview">À installer</span>
        </div>
        {check.fix ? (
          <>
            <p className="text-[13px] leading-relaxed text-foreground/85">
              Ouvre un terminal, colle cette commande, puis clique sur « Vérifier à nouveau ».{' '}
              {/\bsudo\b/.test(check.fix) ? 'Elle demande ton mot de passe et prend quelques minutes.' : 'Elle prend quelques minutes.'}
            </p>
            <div className="flex items-start gap-2.5 rounded-lg bg-foreground px-3.5 py-3 text-background">
              <code className="min-w-0 flex-1 font-mono text-[12.5px] leading-relaxed break-words whitespace-pre-wrap">{check.fix}</code>
              <button
                type="button"
                onClick={() => void copy(check.fix ?? '')}
                className="flex h-7.5 shrink-0 items-center gap-1.5 rounded-md border border-background/20 bg-background/10 px-2.5 text-[12px] hover:bg-background/20"
              >
                <Copy className="size-3.5" /> Copier
              </button>
            </div>
          </>
        ) : (
          <p className="text-[13px] text-foreground/85">
            {system === 'docker' ? "L'image Docker devrait l'avoir : reconstruis-la ou prends la dernière version." : 'Installe-le avec le gestionnaire de paquets de ton système.'}
          </p>
        )}
      </li>
    )
  }
  return (
    <li className={cn('flex flex-wrap items-center gap-x-3.5 gap-y-1.5 px-5 py-3.5', !last && 'border-b', check.ok === null && 'text-muted-foreground')}>
      {check.ok ? <CheckCircle2 className="size-4.5 text-status-offer" aria-hidden="true" /> : <MinusCircle className="size-4.5" aria-hidden="true" />}
      <span className="flex-[1_1_200px] font-medium">{check.label}</span>
      <span className={cn('text-[12px] text-muted-foreground', check.ok && 'font-mono')}>{check.detail}</span>
    </li>
  )
}

/** La liste des vérifications, avec la commande à copier pour chaque manque. */
export function MachineList({ machine, failed }: { machine: Machine | null; failed: string }) {
  if (failed) return <p className="rounded-xl border bg-card surface px-5 py-4 text-[13px] text-destructive">Vérification impossible : {failed}</p>
  if (!machine) return <Skeleton className="h-36 w-full rounded-xl" />
  return (
    <ul aria-label="Vérifications de la machine" className="flex flex-col overflow-hidden rounded-xl border bg-card surface text-[14px]">
      {machine.checks.map((check, i) => (
        <Row key={check.id} check={check} system={machine.system} last={i === machine.checks.length - 1} />
      ))}
    </ul>
  )
}
