import { ArrowLeft, Check, Download, Loader2, RefreshCw, TriangleAlert, UserPlus } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import type { Route } from '@/hooks/use-route'
import { company, dayLabel, nextStep, position, STATUS, where } from '@/lib/applications'
import { api } from '@/lib/api'
import { sinceNow } from '@/lib/format'
import type { AdminPeople, AdminPerson, AdminPersonDetail, CVSummary } from '@/lib/types'
import { cn } from '@/lib/utils'

const money = (value: number) => `${value.toFixed(2).replace('.', ',')} $`

/** En ligne, pour l'administrateur : la liste des personnes, ou une personne en lecture seule. */
export function AdminPage({ email, navigate }: { email?: string; navigate: (route: Route) => void }) {
  return email ? <PersonView email={email} navigate={navigate} /> : <PeopleView navigate={navigate} />
}

function Shell({ title, back, children }: { title: string; back?: () => void; children: React.ReactNode }) {
  return (
    <div className="flex h-full flex-col">
      <header className="flex h-11 shrink-0 items-center gap-3 border-b px-5">
        {back && (
          <button type="button" onClick={back} aria-label="Toutes les personnes" className="text-muted-foreground hover:text-foreground">
            <ArrowLeft className="size-4" />
          </button>
        )}
        <h1 className="truncate text-[13px] font-semibold tracking-tight">{title}</h1>
      </header>
      <ScrollArea className="min-h-0 flex-1">
        <div className="mx-auto flex max-w-5xl flex-col gap-5 px-6 py-7">{children}</div>
      </ScrollArea>
    </div>
  )
}

function PeopleView({ navigate }: { navigate: (route: Route) => void }) {
  const [data, setData] = useState<AdminPeople | null>(null)
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [erasing, setErasing] = useState<AdminPerson | null>(null)

  useEffect(() => {
    api.adminPeople().then(setData, (error: Error) => toast.error('Administration indisponible', { description: error.message }))
  }, [])

  const act = async (key: string, run: () => Promise<AdminPeople>, done: string) => {
    setBusy(key)
    try {
      const next = await run()
      setData(next)
      if (next.warning) toast.warning('Cloudflare', { description: next.warning })
      else toast.success(done)
      return true
    } catch (error) {
      toast.error('Impossible', { description: (error as Error).message })
      return false
    } finally {
      setBusy(null)
    }
  }

  const invite = async (event: React.FormEvent) => {
    event.preventDefault()
    const value = email.trim()
    if (!value) return
    if (await act('invite', () => api.adminInvite(value), `${value.toLowerCase()} invité`)) setEmail('')
  }

  if (!data) {
    return (
      <Shell title="Administration">
        <Skeleton className="h-20 w-full rounded-xl" />
        <Skeleton className="h-60 w-full rounded-xl" />
      </Shell>
    )
  }

  const invited = data.people.filter((p) => !p.admin && !p.removed).length
  return (
    <Shell title="Administration">
      <div>
        <h2 className="text-[22px] font-semibold tracking-tight">Administration</h2>
        <p className="text-[13.5px] text-muted-foreground">
          {invited} personne{invited > 1 ? 's' : ''} invitée{invited > 1 ? 's' : ''}
          {data.spent != null && data.budget != null && ` · IA ce mois : ${money(data.spent)} sur ${money(data.budget)}`}
        </p>
      </div>

      {!data.cloudflare && (
        <p className="flex items-start gap-2 rounded-lg border border-warning/40 bg-warning/10 px-3 py-2 text-[12.5px]">
          <TriangleAlert className="mt-0.5 size-4 shrink-0 text-warning" />
          Cloudflare n'est pas relié : la liste ne change que dans l'appli. Ajoute aussi l'adresse dans Cloudflare Access pour qu'elle
          reçoive un code de connexion.
        </p>
      )}

      <form onSubmit={(e) => void invite(e)} className="flex flex-wrap items-center gap-3 rounded-xl border bg-card surface p-4">
        <Input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="prenom@example.com"
          aria-label="Adresse à inviter"
          className="h-10 min-w-60 flex-1"
        />
        <Button type="submit" disabled={busy !== null || !email.trim()} className="h-10 gap-1.5">
          {busy === 'invite' ? <Loader2 className="size-4 animate-spin" /> : <UserPlus className="size-4" />} Inviter
        </Button>
        <span className="max-w-64 text-[12px] text-muted-foreground">La personne pourra se connecter tout de suite avec un code reçu par e-mail.</span>
      </form>

      <div className="overflow-x-auto rounded-xl border bg-card surface">
        <table className="w-full min-w-[980px] text-[13px]">
          <thead>
            <tr className="border-b text-left text-[11px] tracking-wide text-muted-foreground uppercase">
              <th className="px-4 py-2.5 font-medium">Personne</th>
              <th className="min-w-52 px-4 py-2.5 font-medium">Connexion</th>
              <th className="px-4 py-2.5 font-medium">Dernière visite</th>
              <th className="px-4 py-2.5 font-medium">CV</th>
              <th className="px-4 py-2.5 font-medium">Candidatures</th>
              <th className="px-4 py-2.5 font-medium">IA aujourd'hui</th>
              <th className="px-4 py-2.5" />
            </tr>
          </thead>
          <tbody>
            {data.people.map((p) => {
              const gone = p.removed !== null
              const open = () => navigate({ view: 'admin', email: p.email })
              return (
                <tr
                  key={p.email}
                  className={cn('border-b last:border-0', gone && 'bg-muted/40 text-muted-foreground', mismatch(p) && 'bg-destructive/5')}
                >
                  <td className="px-4 py-3">
                    {p.cvs !== null ? (
                      <button type="button" onClick={open} className="font-semibold text-primary hover:underline">
                        {p.email}
                      </button>
                    ) : (
                      <span className="font-semibold">{p.email}</span>
                    )}
                    {p.admin && <Pill>toi</Pill>}
                    {gone && <Pill>accès retiré</Pill>}
                  </td>
                  <td className="px-4 py-3">
                    <Connection person={p} busy={busy !== null} onRetry={() => void act('sync', () => api.adminSync(), 'Liste envoyée à Cloudflare')} />
                  </td>
                  <td className="px-4 py-3">{p.last_seen ? sinceNow(p.last_seen) : p.admin ? '–' : 'jamais connecté'}</td>
                  <td className="px-4 py-3 tabular-nums">{p.cvs ?? '–'}</td>
                  <td className="px-4 py-3 tabular-nums">
                    {p.applications ?? '–'}
                    {p.due ? <span className="text-status-interview"> · {p.due} relance{p.due > 1 ? 's' : ''}</span> : null}
                  </td>
                  <td className="px-4 py-3 tabular-nums">
                    {!gone && p.ai_left != null && p.ai_quota != null ? `${p.ai_quota - p.ai_left} / ${p.ai_quota}` : '–'}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-2">
                      {p.cvs !== null && (
                        <Button variant="ghost" size="sm" className="h-8" onClick={open}>
                          Voir
                        </Button>
                      )}
                      {!p.admin && !gone && (
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-8"
                          disabled={busy !== null}
                          onClick={() => void act(p.email, () => api.adminRemove(p.email), `Accès de ${p.email} retiré`)}
                        >
                          Retirer l'accès
                        </Button>
                      )}
                      {gone && (
                        <>
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-8"
                            disabled={busy !== null}
                            onClick={() => void act(p.email, () => api.adminInvite(p.email), `${p.email} réinvité`)}
                          >
                            Réinviter
                          </Button>
                          <Button variant="outline" size="sm" className="h-8 text-destructive" disabled={busy !== null} onClick={() => setErasing(p)}>
                            Effacer ses données
                          </Button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="text-[12.5px] text-muted-foreground">
        Retirer l'accès coupe la connexion tout de suite et garde les données. « Effacer ses données » les supprime pour de bon, après
        confirmation.
      </p>

      <AlertDialog open={erasing !== null} onOpenChange={(open) => !open && setErasing(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Effacer les données de {erasing?.email} ?</AlertDialogTitle>
            <AlertDialogDescription>
              Ses CV, lettres, candidatures et sa bibliothèque sont supprimés du serveur, sans retour possible depuis l'appli. Ils
              disparaissent aussi des copies de secours au plus tard 7 jours après.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Garder</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => {
                const target = erasing
                if (target) void act(target.email, () => api.adminErase(target.email), `Données de ${target.email} effacées`)
              }}
            >
              Effacer pour de bon
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Shell>
  )
}

// Cloudflare ne dit pas la même chose que l'appli : la personne ne peut pas entrer (ou le peut encore).
const mismatch = (p: AdminPerson) => p.cloudflare !== null && p.cloudflare === (p.removed !== null)

/** Ce que Cloudflare laisse faire à cette adresse, relu après chaque changement. */
function Connection({ person, busy, onRetry }: { person: AdminPerson; busy: boolean; onRetry: () => void }) {
  if (person.cloudflare === null) return <span className="text-muted-foreground">–</span>
  const gone = person.removed !== null
  const retry = (
    <Button variant="outline" size="sm" className="h-7 gap-1 self-start px-2 text-[12px]" disabled={busy} onClick={onRetry}>
      <RefreshCw className="size-3" /> Réessayer
    </Button>
  )
  if (mismatch(person)) {
    return (
      <div className="flex max-w-60 flex-col gap-1.5">
        <span className="inline-flex items-center gap-1 self-start rounded-full bg-destructive/10 px-2 py-0.5 text-[11.5px] font-semibold whitespace-nowrap text-destructive">
          <TriangleAlert className="size-3" /> {gone ? 'Encore chez Cloudflare' : 'Absent chez Cloudflare'}
        </span>
        <span className="text-[11.5px] text-muted-foreground">
          {gone ? 'Cloudflare lui envoie encore des codes.' : 'Pas de code de connexion tant que la liste n’est pas passée.'}
        </span>
        {retry}
      </div>
    )
  }
  if (gone) return <span className="text-[12px]">ne reçoit plus de code</span>
  return (
    <div className="flex max-w-60 flex-col gap-1">
      <span className="inline-flex items-center gap-1 self-start rounded-full bg-status-offer-soft px-2 py-0.5 text-[11.5px] font-semibold whitespace-nowrap text-status-offer">
        <Check className="size-3" /> Peut recevoir le code
      </span>
      {!person.last_seen && !person.admin && (
        <span className="text-[11.5px] text-muted-foreground">Code pas reçu ? Courrier indésirable, expéditeur Cloudflare.</span>
      )}
    </div>
  )
}

function Pill({ children }: { children: React.ReactNode }) {
  return <span className="ml-2 rounded-full bg-muted px-2 py-0.5 text-[10.5px] font-medium text-muted-foreground">{children}</span>
}

function PersonView({ email, navigate }: { email: string; navigate: (route: Route) => void }) {
  const [detail, setDetail] = useState<AdminPersonDetail | null>(null)
  const [chosen, setChosen] = useState<string | null>(null)

  useEffect(() => {
    api.adminPerson(email).then(
      (found) => {
        setDetail(found)
        const first = found.cvs.find((cv) => cv.meta.kind === 'cv') ?? found.cvs[0]
        setChosen(first?.slug ?? null)
      },
      (error: Error) => toast.error('Personne indisponible', { description: error.message }),
    )
  }, [email])

  const back = () => navigate({ view: 'admin' })
  if (!detail) {
    return (
      <Shell title={email} back={back}>
        <Skeleton className="h-80 w-full rounded-xl" />
      </Shell>
    )
  }
  const targeted = detail.cvs.filter((cv) => cv.meta.kind === 'cv')
  const base = detail.cvs.find((cv) => cv.meta.kind === 'base')
  const shown = detail.cvs.find((cv) => cv.slug === chosen) ?? null

  return (
    <Shell title={email} back={back}>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-[20px] font-semibold tracking-tight">{email}</h2>
          <p className="text-[13px] text-muted-foreground">
            {targeted.length} candidature{targeted.length > 1 ? 's' : ''} · {detail.cvs.length} CV
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded-full bg-status-interview-soft px-3 py-1 text-[12px] font-semibold text-status-interview">
            Lecture seule : rien n'est modifiable ici
          </span>
          <Button asChild variant="outline" size="sm" className="gap-1.5">
            <a href={api.adminExportUrl(email)} download>
              <Download className="size-3.5" /> Télécharger tout (zip)
            </a>
          </Button>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <section className="flex flex-col gap-2 rounded-xl border bg-card surface p-4">
          <h3 className="text-[14px] font-semibold">Candidatures</h3>
          {targeted.length === 0 && <p className="text-[13px] text-muted-foreground">Aucune candidature pour l'instant.</p>}
          {targeted.map((cv) => (
            <CVRow key={cv.slug} cv={cv} active={cv.slug === chosen} onClick={() => setChosen(cv.slug)} />
          ))}
          {base && (
            <>
              <h3 className="pt-3 text-[14px] font-semibold">CV de base</h3>
              <CVRow cv={base} active={base.slug === chosen} onClick={() => setChosen(base.slug)} />
            </>
          )}
        </section>

        <section className="flex min-h-[560px] flex-col gap-2 rounded-xl border bg-card surface p-4">
          <div className="flex items-center justify-between gap-2">
            <h3 className="truncate text-[14px] font-semibold">{shown ? shown.meta.name : 'Aperçu'}</h3>
            {shown?.pdf_version && (
              <a href={api.adminPdfUrl(email, shown.slug, shown.pdf_version)} target="_blank" rel="noreferrer" className="text-[12.5px] font-medium text-primary hover:underline">
                Ouvrir le PDF
              </a>
            )}
          </div>
          {shown?.pdf_version ? (
            <iframe title={`CV ${shown.meta.name}`} src={api.adminPdfUrl(email, shown.slug, shown.pdf_version)} className="min-h-[520px] w-full flex-1 rounded-md border bg-white" />
          ) : (
            <p className="text-[13px] text-muted-foreground">{shown ? "Ce CV n'a pas encore de PDF." : 'Choisis un CV à gauche.'}</p>
          )}
        </section>
      </div>
    </Shell>
  )
}

function CVRow({ cv, active, onClick }: { cv: CVSummary; active: boolean; onClick: () => void }) {
  const isBase = cv.meta.kind === 'base'
  const step = isBase ? null : nextStep(cv)
  const status = STATUS[cv.meta.application.status]
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        'flex items-center justify-between gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors hover:bg-muted/40',
        active && 'border-primary/50 ring-1 ring-primary/20',
      )}
    >
      <span className="flex min-w-0 flex-col">
        <span className="truncate text-[13.5px] font-semibold">{isBase ? cv.meta.name : position(cv)}</span>
        <span className="truncate text-[12px] text-muted-foreground">
          {isBase ? `modifiée le ${dayLabel(cv.meta.updated_at)}` : [company(cv), where(cv)].filter(Boolean).join(' · ')}
        </span>
      </span>
      {!isBase && (
        <span className="flex shrink-0 flex-col items-end gap-1">
          <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-medium', status.pill)}>{status.label}</span>
          {step && <span className={cn('text-[11px]', step.late ? 'text-status-interview' : 'text-muted-foreground')}>{step.text}</span>}
        </span>
      )}
    </button>
  )
}
