import {
  ArrowLeftRight,
  Bold,
  ChevronDown,
  Eye,
  EyeOff,
  Link2,
  MoreHorizontal,
  Plus,
  Trash2,
} from 'lucide-react'
import { closestCorners, DndContext, useDroppable, type DragEndEvent, type DragOverEvent } from '@dnd-kit/core'
import { Fragment, useCallback, useEffect, useRef, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { CvEditor } from '@/hooks/use-cv-editor'
import { at, type FocusRequest } from '@/lib/focus'
import type { Column, ContactItem, CVContent, PageLocation, Section, SectionKind } from '@/lib/types'
import { cn } from '@/lib/utils'
import { AutoTextarea, Field } from './fields'
import { KIND_LABELS, SectionItems } from './section-editors'
import { move, SortableGroup, SortableList, SortableRow, useListSensors } from './sortable'

type Update = CvEditor['update']

interface ContentEditorProps {
  content: CVContent
  update: Update
  focus: FocusRequest | null
  // Mode manuel : le code LaTeX fait foi, le contenu est verrouillé.
  locked: boolean
  // Mise en page à une colonne : une seule liste de rubriques, dans l'ordre du CV.
  oneColumn?: boolean
}

export function ContentEditor({ content, update, focus, locked, oneColumn = false }: ContentEditorProps) {
  const root = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState<ReadonlySet<string>>(() => new Set())
  const [active, setActive] = useState<string | null>(null)

  // Montre la rubrique visée : ouverte, et marquée dans le sommaire.
  const show = (location: PageLocation) => {
    const section = location.area === 'section' ? location.section : null
    setActive(section ?? 'header')
    if (section) setOpen((current) => (current.has(section) ? current : new Set(current).add(section)))
  }

  // Une demande venue de l'extérieur (aperçu, mot-clé) : traitée une fois, au rendu.
  const [handled, setHandled] = useState<number | null>(null)
  if (focus && focus.nonce !== handled) {
    setHandled(focus.nonce)
    show(focus.location)
  }

  // Puis, le temps que la rubrique s'ouvre, on fait défiler jusqu'au champ.
  useEffect(() => {
    if (!focus) return
    const timer = window.setTimeout(() => reveal(root.current, focus.location), 80)
    return () => window.clearTimeout(timer)
  }, [focus])

  const go = (location: PageLocation) => {
    show(location)
    window.setTimeout(() => reveal(root.current, location), 80)
  }

  const toggle = useCallback(
    (id: string, next: boolean) =>
      setOpen((current) => {
        const copy = new Set(current)
        if (next) copy.add(id)
        else copy.delete(id)
        return copy
      }),
    [],
  )

  return (
    <div ref={root} className="@container flex h-full min-h-0">
      <Outline content={content} active={active} onGo={go} disabled={locked} oneColumn={oneColumn} />
      <ScrollArea className="h-full min-w-0 flex-1">
        <fieldset
          disabled={locked}
          aria-label={locked ? 'Verrouillé en mode manuel' : undefined}
          className={cn('mx-auto block max-w-2xl min-w-0 px-5 py-5', locked && 'pointer-events-none opacity-55 select-none')}
        >
          <div className="flex flex-col gap-8 pb-24">
            <HeaderEditor content={content} update={update} />
            {oneColumn ? (
              <ColumnSections column="all" title="Rubriques" content={content} update={update} open={open} onToggle={toggle} />
            ) : (
              <ColumnsBoard content={content} update={update} open={open} onToggle={toggle} />
            )}
          </div>
        </fieldset>
      </ScrollArea>
    </div>
  )
}

/** Fait défiler jusqu'au champ, l'entoure un instant et y place le curseur. */
function reveal(root: HTMLElement | null, location: PageLocation) {
  if (!root) return
  const find = (selector: string) => root.querySelector<HTMLElement>(selector)
  let target: HTMLElement | null = null
  let field: HTMLElement | null = null
  if (location.area === 'header') target = find('[data-block="header"]')
  else if (location.area === 'contact') target = find(`[data-block="contact/${location.line}"]`) ?? find('[data-block="header"]')
  else if (location.section) {
    const id = CSS.escape(location.section)
    const item = location.item != null ? find(`[data-item="${id}/${location.item}"]`) : null
    const bullet = item && location.bullet != null ? find(`[data-item="${id}-${location.item}-bullets/${location.bullet}"]`) : null
    target = item ?? find(`[data-section="${id}"]`)
    field = bullet?.querySelector('textarea') ?? item?.querySelector('textarea, input') ?? null
  }
  if (!target) return
  const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  target.scrollIntoView({ block: 'center', behavior: still ? 'auto' : 'smooth' })
  target.removeAttribute('data-flash')
  void target.offsetWidth
  target.setAttribute('data-flash', '')
  window.setTimeout(() => target.removeAttribute('data-flash'), 1900)
  field?.focus({ preventScroll: true })
}

/** « EXPÉRIENCE PROFESSIONNELLE » → « Expérience professionnelle ». */
function readable(title: string) {
  const lower = title.trim().toLocaleLowerCase('fr')
  return lower ? lower[0].toLocaleUpperCase('fr') + lower.slice(1) : 'Sans titre'
}

interface OutlineProps {
  content: CVContent
  active: string | null
  onGo: (location: PageLocation) => void
  disabled: boolean
  oneColumn: boolean
}

function Outline({ content, active, onGo, disabled, oneColumn }: OutlineProps) {
  const columns: [Column | 'all', string][] = oneColumn
    ? [['all', 'Rubriques']]
    : [
        ['left', 'Colonne de gauche'],
        ['right', 'Colonne de droite'],
      ]
  return (
    <nav aria-label="Sommaire" className="hidden w-40 shrink-0 flex-col gap-0.5 overflow-y-auto border-r px-2 py-4 @[36rem]:flex">
      <p className="px-2 pb-1 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">Sommaire</p>
      <OutlineLink label="En-tête" active={active === 'header'} disabled={disabled} onClick={() => onGo(at(null))} />
      {columns.map(([column, label]) => (
        <Fragment key={column}>
          <p className="mt-3 px-2 pb-0.5 text-[11px] text-muted-foreground">{label}</p>
          {content.sections
            .filter((section) => column === 'all' || section.column === column)
            .map((section) => (
              <OutlineLink
                key={section.id}
                label={readable(section.title)}
                count={section.items.length}
                hidden={!section.visible}
                active={active === section.id}
                disabled={disabled}
                onClick={() => onGo(at(section.id))}
              />
            ))}
        </Fragment>
      ))}
    </nav>
  )
}

interface OutlineLinkProps {
  label: string
  count?: number
  hidden?: boolean
  active: boolean
  disabled: boolean
  onClick: () => void
}

function OutlineLink({ label, count, hidden, active, disabled, onClick }: OutlineLinkProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-current={active ? 'location' : undefined}
      title={hidden ? `${label} (masquée)` : label}
      className={cn(
        'flex h-7 items-center gap-1.5 rounded-md px-2 text-left text-[12.5px] transition-colors disabled:opacity-50',
        active ? 'bg-accent font-medium text-accent-foreground' : 'text-foreground/80 hover:bg-muted',
        hidden && !active && 'text-muted-foreground',
      )}
    >
      <span className="min-w-0 flex-1 truncate">{label}</span>
      {hidden && <EyeOff className="size-3 shrink-0" aria-label="masquée" />}
      {count != null && <span className="shrink-0 font-mono text-[11px] text-muted-foreground tabular-nums">{count}</span>}
    </button>
  )
}

function Block({ title, hint, children, action }: { title: string; hint?: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h2 className="text-[13px] font-semibold tracking-tight">{title}</h2>
          {hint && <p className="mt-0.5 text-[12px] text-muted-foreground">{hint}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  )
}

function HeaderEditor({ content, update }: { content: CVContent; update: Update }) {
  const header = content.header
  return (
    <Block title="En-tête" hint="Nom, titre, accroche et coordonnées.">
      <div data-block="header" className="flex flex-col gap-3 rounded-xl border bg-card surface p-4">
        <Field label="Nom" value={header.name} onChange={(v) => update((d) => void (d.header.name = v), 'header.name')} />
        <Field label="Titre" value={header.headline} onChange={(v) => update((d) => void (d.header.headline = v), 'header.headline')} />
        <Field
          multiline
          label="Accroche"
          placeholder="**gras** et __italique__"
          value={header.summary}
          onChange={(v) => update((d) => void (d.header.summary = v), 'header.summary')}
        />
        <ContactEditor lines={header.contact_lines} update={update} />
      </div>
    </Block>
  )
}

function ContactEditor({ lines, update }: { lines: ContactItem[][]; update: Update }) {
  const edit = (mutate: (lines: ContactItem[][]) => void, group?: string) =>
    update((d) => mutate(d.header.contact_lines), group ?? null)
  return (
    <div className="flex flex-col gap-2">
      <span className="text-[12px] font-medium text-foreground/75">Coordonnées</span>
      {lines.map((line, li) => (
        <div key={li} data-block={`contact/${li}`} className="flex flex-col gap-1.5 rounded-lg border bg-muted/30 p-2.5">
          <div className="flex items-center justify-between">
            <span className="text-[11.5px] font-medium text-muted-foreground">Ligne {li + 1}</span>
            <Button
              variant="ghost"
              size="icon"
              className="size-6 text-muted-foreground"
              aria-label={`Supprimer la ligne ${li + 1}`}
              onClick={() => edit((l) => void l.splice(li, 1))}
            >
              <Trash2 className="size-3" />
            </Button>
          </div>
          <div className="grid grid-cols-[minmax(0,6.5rem)_minmax(0,1fr)_1.75rem_1.75rem_1.75rem] items-center gap-1.5">
            <span className="text-[11px] text-muted-foreground">Libellé</span>
            <span className="text-[11px] text-muted-foreground">Texte</span>
            <span className="text-center text-[11px] text-muted-foreground">Gras</span>
            <span className="text-center text-[11px] text-muted-foreground">Lien</span>
            <span />
            {line.map((item, ii) => {
              const n = `${li + 1}.${ii + 1}`
              const linked = item.url != null
              return (
                <Fragment key={ii}>
                  <AutoTextarea
                    placeholder="aucun"
                    aria-label={`Libellé ${n}`}
                    value={item.label ?? ''}
                    onChange={(e) => edit((l) => void (l[li][ii].label = e.target.value || null), `contact.${li}.${ii}.label`)}
                  />
                  <AutoTextarea
                    placeholder="Texte"
                    aria-label={`Texte ${n}`}
                    value={item.text}
                    onChange={(e) => edit((l) => void (l[li][ii].text = e.target.value), `contact.${li}.${ii}.text`)}
                  />
                  <ToggleButton
                    pressed={Boolean(item.bold)}
                    label="Texte en gras"
                    onClick={() => edit((l) => void (l[li][ii].bold = !l[li][ii].bold))}
                  >
                    <Bold className="size-3.5" />
                  </ToggleButton>
                  <ToggleButton
                    pressed={linked}
                    label={linked ? 'Retirer le lien' : 'Ajouter un lien'}
                    onClick={() => edit((l) => void (l[li][ii].url = linked ? null : 'https://'))}
                  >
                    <Link2 className="size-3.5" />
                  </ToggleButton>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-7 text-muted-foreground"
                    aria-label={`Supprimer la coordonnée ${n}`}
                    onClick={() => edit((l) => void l[li].splice(ii, 1))}
                  >
                    <Trash2 className="size-3" />
                  </Button>
                  {linked && (
                    <label className="col-[2/-1] flex items-center gap-2 pb-1">
                      <span className="shrink-0 text-[11px] text-muted-foreground">Adresse du lien</span>
                      <AutoTextarea
                        className="font-mono text-[12px]"
                        placeholder="https://"
                        value={item.url ?? ''}
                        onChange={(e) => edit((l) => void (l[li][ii].url = e.target.value), `contact.${li}.${ii}.url`)}
                      />
                    </label>
                  )}
                </Fragment>
              )
            })}
          </div>
          <Button variant="ghost" size="sm" className="h-7 self-start px-2 text-[12px] text-muted-foreground" onClick={() => edit((l) => void l[li].push({ text: '' }))}>
            <Plus className="size-3.5" /> Ajouter une coordonnée
          </Button>
        </div>
      ))}
      <Button variant="ghost" size="sm" className="h-7 self-start px-2 text-[12px] text-muted-foreground" onClick={() => edit((l) => void l.push([{ text: '' }]))}>
        <Plus className="size-3.5" /> Ajouter une ligne de coordonnées
      </Button>
    </div>
  )
}

/** Un bouton à deux états (gras, lien), dont l'état se lit sans survol. */
function ToggleButton({ pressed, label, onClick, children }: { pressed: boolean; label: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-pressed={pressed}
          aria-label={label}
          onClick={onClick}
          className={cn(
            'flex size-7 items-center justify-center rounded-md border transition-colors',
            pressed ? 'border-primary/30 bg-accent text-accent-foreground' : 'bg-background text-muted-foreground hover:text-foreground',
          )}
        >
          {children}
        </button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  )
}

const NEW_SECTION: Record<SectionKind, (id: string, column: Column) => Section> = {
  education: (id, column) => ({ id, column, kind: 'education', title: 'FORMATION', visible: true, items: [] }),
  skills: (id, column) => ({ id, column, kind: 'skills', title: 'COMPÉTENCES', visible: true, items: [] }),
  grid: (id, column) => ({ id, column, kind: 'grid', title: 'SOFT SKILLS', visible: true, items: [] }),
  languages: (id, column) => ({ id, column, kind: 'languages', title: 'LANGUES', visible: true, items: [] }),
  bullets: (id, column) => ({ id, column, kind: 'bullets', title: 'NOUVELLE SECTION', visible: true, items: [] }),
  experience: (id, column) => ({ id, column, kind: 'experience', title: 'EXPÉRIENCE', visible: true, layout: 'detailed', items: [] }),
  projects: (id, column) => ({ id, column, kind: 'projects', title: 'PROJETS', visible: true, items: [] }),
}

function newId(content: CVContent, kind: SectionKind): string {
  const taken = new Set(content.sections.map((s) => s.id))
  let n = 1
  while (taken.has(`${kind}-${n}`)) n += 1
  return `${kind}-${n}`
}

const DROP = 'colonne:'

/** Les deux colonnes dans un même glisser-déposer : une rubrique glissée dans l'autre colonne
 * y passe (le menu « Passer dans la colonne… » reste). */
function ColumnsBoard({ content, update, open, onToggle }: Omit<ColumnSectionsProps, 'column' | 'title'>) {
  const sensors = useListSensors()
  const [dragging, setDragging] = useState<string | null>(null)
  const columnOf = (id: string): Column | null => {
    if (id.startsWith(DROP)) return id.slice(DROP.length) as Column
    return content.sections.find((s) => s.id === id)?.column ?? null
  }
  const onDragOver = ({ active, over }: DragOverEvent) => {
    if (!over) return
    const id = String(active.id)
    const target = String(over.id)
    const from = columnOf(id)
    const to = columnOf(target)
    if (!from || !to || from === to) return
    update((d) => {
      const moving = d.sections.find((s) => s.id === id)
      if (!moving) return
      moving.column = to
      const rest = d.sections.filter((s) => s.id !== id)
      let at = rest.findIndex((s) => s.id === target)
      // Lâchée sur la colonne elle-même (vide, ou sous ses rubriques) : à la fin.
      if (at < 0) at = rest.map((s) => s.column).lastIndexOf(to) + 1
      rest.splice(at, 0, moving)
      d.sections = rest
    }, `glisser-${id}`)
  }
  const onDragEnd = ({ active, over }: DragEndEvent) => {
    setDragging(null)
    if (!over || active.id === over.id) return
    const id = String(active.id)
    const target = String(over.id)
    if (target.startsWith(DROP)) return
    update((d) => {
      const from = d.sections.findIndex((s) => s.id === id)
      const to = d.sections.findIndex((s) => s.id === target)
      if (from < 0 || to < 0 || d.sections[from].column !== d.sections[to].column) return
      move(d.sections, from, to)
    }, `glisser-${id}`)
  }
  const draggedColumn = dragging ? columnOf(dragging) : null
  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCorners}
      onDragStart={({ active }) => setDragging(String(active.id))}
      onDragOver={onDragOver}
      onDragEnd={onDragEnd}
      onDragCancel={() => setDragging(null)}
    >
      <ColumnSections column="left" title="Colonne de gauche" content={content} update={update} open={open} onToggle={onToggle} shared dragging={dragging !== null} holds={draggedColumn === 'left'} />
      <ColumnSections column="right" title="Colonne de droite" content={content} update={update} open={open} onToggle={onToggle} shared dragging={dragging !== null} holds={draggedColumn === 'right'} />
    </DndContext>
  )
}

/** La zone d'une colonne où lâcher une rubrique (même vide). */
function DropZone({ column, active, holds, children }: { column: Column; active: boolean; holds: boolean; children: React.ReactNode }) {
  const { setNodeRef } = useDroppable({ id: `${DROP}${column}` })
  return (
    <div
      ref={setNodeRef}
      className={cn(
        '-m-1.5 rounded-2xl p-1.5 transition-colors',
        active && 'outline-2 outline-offset-0 outline-dashed outline-border',
        active && holds && 'bg-accent/40 outline-primary/50',
      )}
    >
      {children}
    </div>
  )
}

interface ColumnSectionsProps {
  // « all » : toutes les rubriques, pour la mise en page à une colonne.
  column: Column | 'all'
  title: string
  content: CVContent
  update: Update
  open: ReadonlySet<string>
  onToggle: (id: string, open: boolean) => void
  // Dans le glisser-déposer commun aux deux colonnes (``ColumnsBoard``).
  shared?: boolean
  dragging?: boolean
  holds?: boolean
}

function ColumnSections({ column, title, content, update, open, onToggle, shared = false, dragging = false, holds = false }: ColumnSectionsProps) {
  const mine = (s: Section) => column === 'all' || s.column === column
  const sections = content.sections.filter(mine)
  const ids = sections.map((s) => s.id)

  // Réordonner dans une colonne : on déplace dans la liste complète.
  const onMove = (from: number, to: number) =>
    update((d) => {
      if (column === 'all') return void move(d.sections, from, to)
      const order = d.sections.filter(mine)
      move(order, from, to)
      const others = d.sections.filter((s) => !mine(s))
      d.sections = column === 'left' ? [...order, ...others] : [...others, ...order]
    })

  const list = (
    <div className="flex flex-col gap-2">
      {sections.map((section) => (
        <SortableRow key={section.id} id={section.id}>
          {(handle) => (
            <SectionCard section={section} handle={handle} update={update} open={open.has(section.id)} onOpenChange={(next) => onToggle(section.id, next)} columns={column !== 'all'} />
          )}
        </SortableRow>
      ))}
      {sections.length === 0 && (
        <p className="rounded-xl border border-dashed p-6 text-center text-[12px] text-muted-foreground">
          {shared ? 'Aucune section dans cette colonne : glisses-en une ici.' : 'Aucune section dans cette colonne.'}
        </p>
      )}
    </div>
  )

  return (
    <Block
      title={title}
      hint={
        shared
          ? "Glisse une section pour la réordonner ou la passer dans l'autre colonne. L'œil la masque sans la supprimer."
          : "Glisser pour réordonner. L'œil masque une section sans la supprimer."
      }
      action={
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm" className="h-7 gap-1 px-2 text-[12px]">
              <Plus className="size-3.5" /> Section
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-48">
            <DropdownMenuLabel className="text-[11px] text-muted-foreground">Type de section</DropdownMenuLabel>
            {(Object.keys(NEW_SECTION) as SectionKind[]).map((kind) => (
              <DropdownMenuItem
                key={kind}
                onSelect={() => update((d) => void d.sections.push(NEW_SECTION[kind](newId(d, kind), column === 'all' ? 'left' : column)))}
              >
                {KIND_LABELS[kind]}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      }
    >
      {shared && column !== 'all' ? (
        <DropZone column={column} active={dragging} holds={holds}>
          <SortableGroup ids={ids}>{list}</SortableGroup>
        </DropZone>
      ) : (
        <SortableList ids={ids} onMove={onMove}>
          {list}
        </SortableList>
      )}
    </Block>
  )
}

interface SectionCardProps {
  section: Section
  handle: React.ReactNode
  update: Update
  open: boolean
  onOpenChange: (open: boolean) => void
  // Deux colonnes : la rubrique peut changer de colonne.
  columns: boolean
}

function SectionCard({ section, handle, update, open, onOpenChange, columns }: SectionCardProps) {
  const edit = (mutate: (s: Section) => void, group?: string) =>
    update((d) => {
      const target = d.sections.find((s) => s.id === section.id)
      if (target) mutate(target)
    }, group ?? null)
  const count = section.items.length

  return (
    <Collapsible open={open} onOpenChange={onOpenChange}>
      <div data-section={section.id} className={cn('rounded-xl border bg-card surface transition-shadow', open && 'shadow-md', !section.visible && 'opacity-60')}>
        <div className="flex items-center gap-1 py-1.5 pr-1.5 pl-1">
          {handle}
          <input
            value={section.title}
            onChange={(e) => edit((s) => void (s.title = e.target.value), `${section.id}.title`)}
            className="h-7 min-w-0 flex-1 rounded-md bg-transparent px-1.5 text-[13px] font-semibold tracking-tight outline-none hover:bg-muted/60 focus:bg-muted/60"
            aria-label="Titre de la section"
          />
          <Badge variant="secondary" className="h-5 shrink-0 px-1.5 text-[10px] font-normal">
            {KIND_LABELS[section.kind]} · {count}
          </Badge>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="size-7 text-muted-foreground"
                aria-label={section.visible ? 'Masquer la section' : 'Afficher la section'}
                onClick={() => edit((s) => void (s.visible = !s.visible))}
              >
                {section.visible ? <Eye className="size-3.5" /> : <EyeOff className="size-3.5" />}
              </Button>
            </TooltipTrigger>
            <TooltipContent>{section.visible ? 'Masquer' : 'Afficher'}</TooltipContent>
          </Tooltip>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="size-7 text-muted-foreground" aria-label="Actions">
                <MoreHorizontal className="size-3.5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              {columns && (
                <DropdownMenuItem onSelect={() => edit((s) => void (s.column = s.column === 'left' ? 'right' : 'left'))}>
                <ArrowLeftRight className="size-3.5" />
                Passer dans la colonne {section.column === 'left' ? 'de droite' : 'de gauche'}
              </DropdownMenuItem>
              )}
              {section.kind === 'experience' && (
                <DropdownMenuItem
                  onSelect={() => edit((s) => {
                    if (s.kind === 'experience') s.layout = s.layout === 'detailed' ? 'compact' : 'detailed'
                  })}
                >
                  Présentation {section.layout === 'detailed' ? 'compacte' : 'détaillée'}
                </DropdownMenuItem>
              )}
              <DropdownMenuSeparator />
              <DropdownMenuItem
                variant="destructive"
                onSelect={() => update((d) => void (d.sections = d.sections.filter((s) => s.id !== section.id)))}
              >
                <Trash2 className="size-3.5" />
                Supprimer la section
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <CollapsibleTrigger asChild>
            <Button variant="ghost" size="icon" className="size-7 text-muted-foreground" aria-label={open ? 'Replier' : 'Déplier'}>
              <ChevronDown className={cn('size-3.5 transition-transform duration-200', open && 'rotate-180')} />
            </Button>
          </CollapsibleTrigger>
        </div>
        <CollapsibleContent>
          <div className="border-t px-3 pt-3 pb-2">
            <SectionItems
              section={section}
              edit={(mutate, group) => edit((s) => mutate(s.items as unknown[]), group)}
            />
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  )
}
