import { BellRing, CalendarDays, Columns3, Copy, Download, FileCode2, FilePlus2, LayoutGrid, MoreHorizontal, PencilLine, Search, Sparkles, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { api } from '@/lib/api'
import { company, lateText, monogram, nextStep, position, STATUS, STATUS_ORDER, where } from '@/lib/applications'
import type { ApplicationStatus, CVSummary } from '@/lib/types'
import { cn } from '@/lib/utils'

import { ApplicationSheet } from './application-sheet'
import { DeleteDialog, NewCVDialog, RenameDialog } from './dialogs'

type Sort = 'recent' | 'score' | 'name'
type View = 'cards' | 'board'
type Filter = 'all' | ApplicationStatus

const VIEW_KEY = 'cv-builder.applications.view'
const fold = (text: string) => text.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase()

function storedView(): View {
  try {
    return localStorage.getItem(VIEW_KEY) === 'board' ? 'board' : 'cards'
  } catch {
    return 'cards'
  }
}

// La dernière activité : le dernier événement du suivi, sinon la création du CV.
const activity = (cv: CVSummary) => cv.meta.application.history[0]?.on ?? cv.meta.created_at.slice(0, 10)

interface ApplicationsPageProps {
  cvs: CVSummary[] | null
  onOpen: (slug: string) => void
  onTarget: () => void
  refresh: () => Promise<void>
}

/** Les candidatures : un CV ciblé par offre, et où en est chacune. */
export function ApplicationsPage({ cvs, onOpen, onTarget, refresh }: ApplicationsPageProps) {
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<Sort>('recent')
  const [filter, setFilter] = useState<Filter>('all')
  const [view, setView] = useState<View>(storedView)
  const [opened, setOpened] = useState<string | null>(null)
  const [patched, setPatched] = useState<Record<string, CVSummary>>({})
  const [creating, setCreating] = useState<{ source: string; name: string } | null>(null)
  const [renaming, setRenaming] = useState<CVSummary | null>(null)
  const [deleting, setDeleting] = useState<CVSummary | null>(null)

  // À chaque ouverture de la page : un ciblage ou une fiche ont pu changer la liste.
  useEffect(() => {
    void refresh()
  }, [refresh])

  const items = useMemo(
    () => (cvs ?? []).filter((cv) => cv.meta.kind === 'cv').map((cv) => patched[cv.slug] ?? cv),
    [cvs, patched],
  )
  const shown = useMemo(() => {
    const needle = fold(query.trim())
    const found = items.filter((cv) => fold([cv.meta.name, company(cv), position(cv), cv.location].join(' ')).includes(needle))
    return found.sort((a, b) =>
      sort === 'score'
        ? (b.meta.score ?? -1) - (a.meta.score ?? -1)
        : sort === 'name'
          ? company(a).localeCompare(company(b), 'fr')
          : activity(b).localeCompare(activity(a)),
    )
  }, [items, query, sort])
  const visible = filter === 'all' ? shown : shown.filter((cv) => cv.meta.application.status === filter)
  const due = items.filter((cv) => cv.due)
  const count = (status: ApplicationStatus) => items.filter((cv) => cv.meta.application.status === status).length
  const current = opened ? (items.find((cv) => cv.slug === opened) ?? null) : null

  const chooseView = (next: View) => {
    setView(next)
    try {
      localStorage.setItem(VIEW_KEY, next)
    } catch {
      /* stockage indisponible : le choix vaut pour cette visite */
    }
  }
  const saved = (cv: CVSummary) => {
    setPatched((before) => ({ ...before, [cv.slug]: cv }))
    void refresh().then(() => setPatched((before) => {
      const { [cv.slug]: _, ...rest } = before
      return rest
    }))
  }
  const update = async (cv: CVSummary, patch: Parameters<typeof api.updateApplication>[1]) => {
    try {
      saved(await api.updateApplication(cv.slug, patch))
    } catch (error) {
      toast.error('Enregistrement impossible', { description: error instanceof Error ? error.message : String(error) })
    }
  }
  const actions = (cv: CVSummary) => ({
    onSheet: () => setOpened(cv.slug),
    onOpen: () => onOpen(cv.slug),
    onDuplicate: () => setCreating({ source: cv.slug, name: `${cv.meta.name} (copie)` }),
    onRename: () => setRenaming(cv),
    onDelete: () => setDeleting(cv),
  })

  const interviews = count('interview')
  return (
    <div className="flex h-full flex-col">
      <ScrollArea className="min-h-0 flex-1">
        <div className="mx-auto flex max-w-[1180px] flex-col gap-6 px-8 pt-7 pb-12">
          <header className="flex flex-wrap items-end gap-3">
            <div className="flex min-w-64 flex-1 flex-col gap-1">
              <h1 className="text-[26px] font-semibold tracking-tight">Candidatures</h1>
              <p className="text-[13.5px] text-muted-foreground">
                {cvs === null ? 'Chargement…' : `${items.length} offre${items.length > 1 ? 's' : ''} ciblée${items.length > 1 ? 's' : ''}`}
                {due.length > 0 && (
                  <span className="font-semibold text-status-interview"> · {due.length} relance{due.length > 1 ? 's' : ''} à faire</span>
                )}
                {interviews > 0 && ` · ${interviews} entretien${interviews > 1 ? 's' : ''}`}
              </p>
            </div>
            <label className="flex h-9 w-full max-w-72 items-center gap-2 rounded-lg border bg-background px-3 shadow-xs focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/40">
              <Search className="size-4 text-muted-foreground" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Entreprise, poste, ville…"
                aria-label="Rechercher une candidature"
                className="min-w-0 flex-1 bg-transparent text-[13px] outline-none placeholder:text-muted-foreground"
              />
            </label>
            <Button variant="outline" className="h-9 gap-1.5" onClick={() => setCreating({ source: 'base', name: '' })}>
              <FilePlus2 className="size-4" /> Nouveau CV
            </Button>
            <Button className="h-9 gap-1.5" onClick={onTarget}>
              <Sparkles className="size-4" /> Cibler une offre
            </Button>
          </header>

          {due.length > 0 && (
            <section aria-label="À relancer" className="flex flex-col gap-3 rounded-xl border border-status-interview/25 bg-status-interview-soft/60 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <BellRing className="size-4 text-status-interview" />
                <h2 className="text-[13.5px] font-semibold text-status-interview">À relancer</h2>
                <span className="text-[12.5px] text-muted-foreground">Sans réponse dix jours après l'envoi.</span>
              </div>
              {due.map((cv) => {
                const mono = monogram(cv)
                return (
                  <div key={cv.slug} className="flex flex-wrap items-center gap-3 rounded-lg border bg-card surface px-3 py-2.5">
                    <span className={cn('flex size-9 shrink-0 items-center justify-center rounded-lg text-[14px] font-bold', mono.tint)}>{mono.letter}</span>
                    <div className="flex min-w-60 flex-1 flex-col">
                      <span className="truncate text-[13.5px] font-semibold">
                        {company(cv)} · {position(cv)}
                      </span>
                      <span className="text-[12.5px] text-status-interview">{lateText(cv.meta.application.follow_up_on ?? '')}</span>
                    </div>
                    <Button size="sm" variant="outline" className="h-8" onClick={() => setOpened(cv.slug)}>
                      Préparer la relance
                    </Button>
                    <Button size="sm" variant="ghost" className="h-8 text-status-interview" onClick={() => void update(cv, { followed_up: true })}>
                      Relancée aujourd'hui
                    </Button>
                  </div>
                )
              })}
            </section>
          )}

          <div className="flex flex-wrap items-center gap-2.5">
            <div role="group" aria-label="Filtrer par statut" className="flex flex-1 flex-wrap gap-1.5">
              {(['all', ...STATUS_ORDER] as Filter[]).map((key) => {
                const active = filter === key
                return (
                  <button
                    key={key}
                    type="button"
                    aria-pressed={active}
                    onClick={() => setFilter(key)}
                    className={cn(
                      'flex h-8 items-center gap-1.5 rounded-full border px-3 text-[12.5px] font-medium transition-colors focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none',
                      active ? 'border-primary/60 bg-accent font-semibold text-accent-foreground' : 'bg-card hover:bg-muted',
                    )}
                  >
                    {key === 'all' ? 'Toutes' : STATUS[key].plural}
                    <span className={cn('font-mono text-[11.5px] tabular-nums', active ? 'text-accent-foreground/75' : 'text-muted-foreground')}>
                      {key === 'all' ? items.length : count(key)}
                    </span>
                  </button>
                )
              })}
            </div>
            <Select value={sort} onValueChange={(v) => setSort(v as Sort)}>
              <SelectTrigger size="sm" className="h-8 w-44 text-[12.5px]" aria-label="Trier">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="recent" className="text-[12.5px]">Activité récente</SelectItem>
                <SelectItem value="score" className="text-[12.5px]">Meilleure correspondance</SelectItem>
                <SelectItem value="name" className="text-[12.5px]">Par entreprise</SelectItem>
              </SelectContent>
            </Select>
            <div role="radiogroup" aria-label="Affichage" className="flex gap-0.5 rounded-lg bg-muted p-0.5">
              {(
                [
                  ['cards', 'Cartes', <LayoutGrid key="i" className="size-3.5" />],
                  ['board', 'Colonnes', <Columns3 key="i" className="size-3.5" />],
                ] as const
              ).map(([key, label, icon]) => (
                <button
                  key={key}
                  type="button"
                  role="radio"
                  aria-checked={view === key}
                  onClick={() => chooseView(key)}
                  className={cn(
                    'flex h-7 items-center gap-1.5 rounded-md px-2.5 text-[12.5px] font-medium transition-colors focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none',
                    view === key ? 'bg-background shadow-xs' : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  {icon}
                  {label}
                </button>
              ))}
            </div>
          </div>

          {cvs === null && (
            <div className="grid grid-cols-[repeat(auto-fill,minmax(270px,1fr))] gap-4">
              {[0, 1, 2].map((i) => (
                <div key={i} className="h-48 animate-pulse rounded-xl bg-muted" />
              ))}
            </div>
          )}

          {cvs !== null && items.length === 0 && (
            <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed px-6 py-16 text-center">
              <p className="max-w-md text-[13.5px] text-muted-foreground">
                Aucune candidature pour l'instant. Cible une offre : l'appli adapte ton CV, et la candidature apparaît ici pour en suivre
                l'envoi, les relances et les réponses.
              </p>
              <Button onClick={onTarget} className="gap-1.5">
                <Sparkles className="size-4" /> Cibler une offre
              </Button>
            </div>
          )}

          {items.length > 0 && view === 'cards' && (
            <div className="grid grid-cols-[repeat(auto-fill,minmax(270px,1fr))] gap-4">
              {visible.map((cv) => (
                <Card key={cv.slug} cv={cv} {...actions(cv)} />
              ))}
              {visible.length === 0 && (
                <p className="col-span-full py-12 text-center text-[13px] text-muted-foreground">Aucune candidature ici pour l'instant.</p>
              )}
            </div>
          )}

          {items.length > 0 && view === 'board' && (
            <Board items={shown} onMove={(cv, status) => void update(cv, { status })} actions={actions} />
          )}
        </div>
      </ScrollArea>

      <ApplicationSheet cv={current} onClose={() => setOpened(null)} onOpenCV={onOpen} onSaved={saved} />
      <NewCVDialog
        state={creating}
        cvs={cvs ?? []}
        onClose={() => setCreating(null)}
        onCreated={async (slug) => {
          setCreating(null)
          await refresh()
          onOpen(slug)
        }}
      />
      <RenameDialog cv={renaming} onClose={() => setRenaming(null)} onDone={async () => { setRenaming(null); await refresh() }} />
      <DeleteDialog cv={deleting} onClose={() => setDeleting(null)} onDone={async () => { setDeleting(null); await refresh() }} />
    </div>
  )
}

interface CardActions {
  onSheet: () => void
  onOpen: () => void
  onDuplicate: () => void
  onRename: () => void
  onDelete: () => void
}

function Card({ cv, onSheet, ...menu }: { cv: CVSummary } & CardActions) {
  const mono = monogram(cv)
  const status = cv.meta.application.status
  const step = nextStep(cv)
  const score = cv.meta.score
  return (
    <article className="group/card relative flex flex-col gap-3.5 rounded-xl border bg-card surface p-4 transition-shadow hover:border-foreground/15 hover:shadow-md">
      <div className="flex items-center gap-2.5">
        <span className={cn('flex size-9 shrink-0 items-center justify-center rounded-lg text-[14px] font-bold', mono.tint)}>{mono.letter}</span>
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="truncate text-[13px] font-semibold">{company(cv)}</span>
          <span className="truncate text-[12px] text-muted-foreground">{where(cv)}</span>
        </div>
        <span className={cn('shrink-0 rounded-full px-2.5 py-0.5 text-[11.5px] font-semibold', STATUS[status].pill)}>{STATUS[status].label}</span>
      </div>
      <button
        type="button"
        onClick={onSheet}
        className="line-clamp-2 min-h-10 text-left text-[14.5px] leading-snug font-semibold tracking-tight after:absolute after:inset-0 after:rounded-xl focus-visible:outline-none focus-visible:after:ring-[3px] focus-visible:after:ring-ring/50"
      >
        {position(cv)}
      </button>
      <div className="flex flex-col gap-1.5">
        <div className="flex justify-between text-[12px] text-muted-foreground">
          <span>Correspondance à l'offre</span>
          <span className="font-mono font-medium text-foreground tabular-nums">{score != null ? `${score} %` : '—'}</span>
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-muted">
          <div
            className={cn('h-full rounded-full', score == null ? '' : score >= 75 ? 'bg-primary' : score >= 50 ? 'bg-primary/65' : 'bg-primary/35')}
            style={{ width: `${score ?? 0}%` }}
          />
        </div>
      </div>
      <div className="flex items-center gap-2 border-t pt-3 text-[12.5px]">
        <CalendarDays className="size-3.5 shrink-0 text-muted-foreground" />
        <span className={cn('min-w-0 flex-1 truncate', step.late ? 'font-semibold text-status-interview' : 'text-muted-foreground')}>{step.text}</span>
        <CardMenu cv={cv} onSheet={onSheet} {...menu} />
      </div>
    </article>
  )
}

function CardMenu({ cv, onSheet, onOpen, onDuplicate, onRename, onDelete }: { cv: CVSummary } & CardActions) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="relative z-10 -my-1 size-7 shrink-0 text-muted-foreground" aria-label={`Actions pour ${cv.meta.name}`}>
          <MoreHorizontal className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-52">
        <DropdownMenuItem onSelect={onOpen}>Ouvrir le CV</DropdownMenuItem>
        <DropdownMenuItem onSelect={onSheet}>Fiche de candidature</DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={onDuplicate}><Copy className="size-3.5" /> Dupliquer</DropdownMenuItem>
        <DropdownMenuItem onSelect={onRename}><PencilLine className="size-3.5" /> Renommer</DropdownMenuItem>
        <DropdownMenuItem asChild disabled={!cv.pdf_version}>
          <a href={api.pdfUrl(cv.slug, cv.pdf_version)} download={`${cv.file_stem}.pdf`}><Download className="size-3.5" /> Télécharger le PDF</a>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <a href={api.texUrl(cv.slug)} download={`${cv.file_stem}.tex`}><FileCode2 className="size-3.5" /> Télécharger le .tex</a>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem variant="destructive" onSelect={onDelete}><Trash2 className="size-3.5" /> Supprimer</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function Board({ items, onMove, actions }: { items: CVSummary[]; onMove: (cv: CVSummary, status: ApplicationStatus) => void; actions: (cv: CVSummary) => CardActions }) {
  const [over, setOver] = useState<ApplicationStatus | null>(null)
  const drop = (status: ApplicationStatus, slug: string) => {
    setOver(null)
    const cv = items.find((item) => item.slug === slug)
    if (cv && cv.meta.application.status !== status) onMove(cv, status)
  }
  return (
    <div className="overflow-x-auto pb-2">
      <div className="grid min-w-[1080px] grid-cols-5 gap-3">
        {STATUS_ORDER.map((status) => {
          const column = items.filter((cv) => cv.meta.application.status === status)
          return (
            <section
              key={status}
              aria-label={STATUS[status].label}
              onDragOver={(e) => {
                e.preventDefault()
                setOver(status)
              }}
              onDragLeave={() => setOver((current) => (current === status ? null : current))}
              onDrop={(e) => {
                e.preventDefault()
                drop(status, e.dataTransfer.getData('text/plain'))
              }}
              className={cn('flex min-h-96 flex-col gap-2.5 rounded-xl bg-muted/70 p-2.5 transition-colors', over === status && 'bg-primary/10 ring-2 ring-primary/30')}
            >
              <div className="flex items-center gap-2 px-1.5 pt-1">
                <span className={cn('size-2 rounded-full', STATUS[status].dot)} />
                <h2 className="text-[13px] font-semibold">{STATUS[status].label}</h2>
                <span className="ml-auto font-mono text-[11.5px] text-muted-foreground tabular-nums">{column.length}</span>
              </div>
              {column.map((cv) => {
                const mono = monogram(cv)
                const step = nextStep(cv)
                const { onSheet } = actions(cv)
                return (
                  <article
                    key={cv.slug}
                    draggable
                    onDragStart={(e) => {
                      e.dataTransfer.setData('text/plain', cv.slug)
                      e.dataTransfer.effectAllowed = 'move'
                    }}
                    className="relative flex cursor-grab flex-col gap-2 rounded-lg border bg-card surface p-3 transition-shadow hover:shadow-md active:cursor-grabbing"
                  >
                    <div className="flex items-center gap-2">
                      <span className={cn('flex size-6 shrink-0 items-center justify-center rounded-md text-[11px] font-bold', mono.tint)}>{mono.letter}</span>
                      <span className="min-w-0 flex-1 truncate text-[12.5px] font-semibold">{company(cv)}</span>
                      {cv.meta.score != null && <span className="font-mono text-[11.5px] text-muted-foreground tabular-nums">{cv.meta.score} %</span>}
                    </div>
                    <button
                      type="button"
                      onClick={onSheet}
                      className="line-clamp-2 text-left text-[13px] leading-snug font-semibold after:absolute after:inset-0 after:rounded-lg focus-visible:outline-none focus-visible:after:ring-[3px] focus-visible:after:ring-ring/50"
                    >
                      {position(cv)}
                    </button>
                    <span className={cn('text-[11.5px]', step.late ? 'font-semibold text-status-interview' : 'text-muted-foreground')}>{step.text}</span>
                  </article>
                )
              })}
              {column.length === 0 && (
                <p className="rounded-lg border border-dashed px-3 py-5 text-center text-[12px] text-muted-foreground">
                  Glisse une carte ici quand ça avance.
                </p>
              )}
            </section>
          )
        })}
      </div>
    </div>
  )
}
