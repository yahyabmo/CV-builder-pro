import { BookMarked, Plus, Trash2 } from 'lucide-react'
import { useState, type ReactNode } from 'react'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { api } from '@/lib/api'
import type {
  EducationItem,
  LibraryProject,
  ExperienceItem,
  GridItem,
  Language,
  ProjectItem,
  Section,
  SkillGroup,
} from '@/lib/types'
import { AutoTextarea, Field } from './fields'
import { move, SortableList, SortableRow } from './sortable'

/** Modifie les éléments de la section (copie de travail) ; `group` regroupe les frappes. */
export type EditItems<T> = (mutate: (items: T[]) => void, group?: string) => void

interface ItemListProps<T> {
  prefix: string
  items: T[]
  edit: EditItems<T>
  addLabel: string
  newItem: () => T
  children: (item: T, index: number) => ReactNode
  compact?: boolean
}

/** Liste d'éléments réordonnables, avec ajout et suppression. */
function ItemList<T>({ prefix, items, edit, addLabel, newItem, children, compact }: ItemListProps<T>) {
  const ids = items.map((_, index) => `${prefix}-${index}`)
  return (
    <div className="flex flex-col gap-2">
      <SortableList ids={ids} onMove={(from, to) => edit((list) => move(list, from, to))}>
        {items.map((item, index) => (
          <SortableRow key={ids[index]} id={ids[index]}>
            {(handle) => (
              <div
                data-item={`${prefix}/${index}`}
                className={
                  compact
                    ? 'group/item flex items-start gap-1'
                    : 'group/item flex items-start gap-1 rounded-lg border bg-card surface p-2.5 pl-1'
                }
              >
                {handle}
                <div className="min-w-0 flex-1">{children(item, index)}</div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-7 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover/item:opacity-100 focus-visible:opacity-100"
                  aria-label="Supprimer"
                  onClick={() => edit((list) => void list.splice(index, 1))}
                >
                  <Trash2 className="size-3.5" />
                </Button>
              </div>
            )}
          </SortableRow>
        ))}
      </SortableList>
      <Button
        variant="ghost"
        size="sm"
        className="h-7 self-start px-2 text-[12px] text-muted-foreground"
        onClick={() => edit((list) => void list.push(newItem()))}
      >
        <Plus className="size-3.5" />
        {addLabel}
      </Button>
    </div>
  )
}

const RICH_HINT = '**gras** et __italique__'

function EducationEditor({ id, items, edit }: { id: string; items: EducationItem[]; edit: EditItems<EducationItem> }) {
  return (
    <ItemList
      prefix={id}
      items={items}
      edit={edit}
      addLabel="Ajouter une formation"
      newItem={() => ({ title: '', place: '', dates: '', description: '' })}
    >
      {(item, i) => (
        <div className="grid grid-cols-2 gap-2">
          <Field className="col-span-2" label="Diplôme" value={item.title} onChange={(v) => edit((l) => void (l[i].title = v), `${id}.${i}.title`)} />
          <Field label="Établissement" value={item.place} onChange={(v) => edit((l) => void (l[i].place = v), `${id}.${i}.place`)} />
          <Field label="Dates" value={item.dates} onChange={(v) => edit((l) => void (l[i].dates = v), `${id}.${i}.dates`)} />
          <Field className="col-span-2" multiline label="Description" placeholder={RICH_HINT} value={item.description} onChange={(v) => edit((l) => void (l[i].description = v), `${id}.${i}.description`)} />
        </div>
      )}
    </ItemList>
  )
}

function SkillsEditor({ id, items, edit }: { id: string; items: SkillGroup[]; edit: EditItems<SkillGroup> }) {
  return (
    <ItemList prefix={id} items={items} edit={edit} addLabel="Ajouter un groupe" newItem={() => ({ label: '', text: '' })}>
      {(item, i) => (
        <div className="flex flex-col gap-2">
          <Field label="Groupe" value={item.label} onChange={(v) => edit((l) => void (l[i].label = v), `${id}.${i}.label`)} />
          <Field multiline label="Compétences" placeholder={RICH_HINT} value={item.text} onChange={(v) => edit((l) => void (l[i].text = v), `${id}.${i}.text`)} />
        </div>
      )}
    </ItemList>
  )
}

function GridEditor({ id, items, edit }: { id: string; items: GridItem[]; edit: EditItems<GridItem> }) {
  return (
    <ItemList prefix={id} items={items} edit={edit} addLabel="Ajouter une case" newItem={(): GridItem => ({ text: '' })} compact>
      {(item, i) => (
        <div className="flex items-center gap-3">
          <AutoTextarea value={item.text} onChange={(e) => edit((l) => void (l[i].text = e.target.value), `${id}.${i}.text`)} />
          <div className="flex shrink-0 items-center gap-1.5">
            <Switch
              id={`${id}-${i}-wide`}
              checked={Boolean(item.wide)}
              onCheckedChange={(checked) => edit((l) => void (l[i].wide = checked))}
            />
            <Label htmlFor={`${id}-${i}-wide`} className="text-[11px] font-normal text-muted-foreground">
              Ligne entière
            </Label>
          </div>
        </div>
      )}
    </ItemList>
  )
}

function LanguagesEditor({ id, items, edit }: { id: string; items: Language[]; edit: EditItems<Language> }) {
  return (
    <ItemList prefix={id} items={items} edit={edit} addLabel="Ajouter une langue" newItem={() => ({ name: '', level: '' })} compact>
      {(item, i) => (
        <div className="grid grid-cols-[1fr_1.4fr] gap-2">
          <AutoTextarea placeholder="Langue" value={item.name} onChange={(e) => edit((l) => void (l[i].name = e.target.value), `${id}.${i}.name`)} />
          <AutoTextarea placeholder="Niveau" value={item.level} onChange={(e) => edit((l) => void (l[i].level = e.target.value), `${id}.${i}.level`)} />
        </div>
      )}
    </ItemList>
  )
}

function BulletsEditor({ id, items, edit, addLabel = 'Ajouter une ligne' }: { id: string; items: string[]; edit: EditItems<string>; addLabel?: string }) {
  return (
    <ItemList prefix={id} items={items} edit={edit} addLabel={addLabel} newItem={() => ''} compact>
      {(item, i) => (
        <AutoTextarea placeholder={RICH_HINT} value={item} onChange={(e) => edit((l) => void (l[i] = e.target.value), `${id}.${i}`)} />
      )}
    </ItemList>
  )
}

function ExperienceEditor({ id, items, edit }: { id: string; items: ExperienceItem[]; edit: EditItems<ExperienceItem> }) {
  return (
    <ItemList
      prefix={id}
      items={items}
      edit={edit}
      addLabel="Ajouter une expérience"
      newItem={() => ({ title: '', tag: '', place: '', dates: '', bullets: [] })}
    >
      {(item, i) => (
        <div className="flex flex-col gap-2">
          <div className="grid grid-cols-2 gap-2">
            <Field label="Intitulé" value={item.title} onChange={(v) => edit((l) => void (l[i].title = v), `${id}.${i}.title`)} />
            <Field label="Mention" placeholder="Projet mené en autonomie" value={item.tag} onChange={(v) => edit((l) => void (l[i].tag = v), `${id}.${i}.tag`)} />
            <Field label="Lieu" value={item.place} onChange={(v) => edit((l) => void (l[i].place = v), `${id}.${i}.place`)} />
            <Field label="Dates" value={item.dates} onChange={(v) => edit((l) => void (l[i].dates = v), `${id}.${i}.dates`)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <span className="text-[12px] font-medium text-foreground/75">Puces</span>
            <BulletsEditor
              id={`${id}-${i}-bullets`}
              items={item.bullets}
              addLabel="Ajouter une puce"
              edit={(mutate, group) => edit((l) => mutate(l[i].bullets), group)}
            />
          </div>
        </div>
      )}
    </ItemList>
  )
}

const TEAM_TAG = { seul: 'Projet individuel', binôme: 'En binôme', équipe: 'En équipe' } as const

/** Un projet validé de la bibliothèque, ajouté au CV en un clic. */
function FromLibrary({ items, edit }: { items: ProjectItem[]; edit: EditItems<ProjectItem> }) {
  const [projects, setProjects] = useState<LibraryProject[] | null>(null)
  const present = new Set(items.map((item) => item.library_id).filter(Boolean))
  return (
    <DropdownMenu
      onOpenChange={(open) => {
        if (open) api.getLibrary().then((lib) => setProjects(lib.projects.filter((p) => p.status === 'validé'))).catch(() => setProjects([]))
      }}
    >
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm" className="h-7 self-start px-2 text-[12px] text-muted-foreground">
          <BookMarked className="size-3.5" /> Depuis la bibliothèque
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="max-h-80 w-72 overflow-y-auto">
        <DropdownMenuLabel className="text-[11px] text-muted-foreground">Projets validés</DropdownMenuLabel>
        {projects === null && <p className="px-2 py-1.5 text-[12px] text-muted-foreground">Chargement…</p>}
        {projects?.length === 0 && <p className="px-2 py-1.5 text-[12px] text-muted-foreground">Aucun projet validé dans la bibliothèque.</p>}
        {projects?.map((project) => (
          <DropdownMenuItem
            key={project.id}
            disabled={present.has(project.id)}
            onSelect={() =>
              edit((list) =>
                void list.push({
                  title: project.title,
                  tag: project.team ? TEAM_TAG[project.team] : '',
                  date: project.date,
                  description: project.description,
                  link: project.link,
                  library_id: project.id,
                }),
              )
            }
            className="flex flex-col items-start gap-0"
          >
            <span className="text-[12.5px]">{project.title}</span>
            <span className="text-[11px] text-muted-foreground">{present.has(project.id) ? 'déjà dans ce CV' : [project.date, ...project.techs.slice(0, 3)].filter(Boolean).join(' · ')}</span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function ProjectsEditor({ id, items, edit }: { id: string; items: ProjectItem[]; edit: EditItems<ProjectItem> }) {
  return (
    <div className="flex flex-col gap-1">
    <ItemList
      prefix={id}
      items={items}
      edit={edit}
      addLabel="Ajouter un projet"
      newItem={(): ProjectItem => ({ title: '', tag: '', date: '', description: '' })}
    >
      {(item, i) => (
        <div className="grid grid-cols-[1fr_7rem] gap-2">
          <Field label="Titre" value={item.title} onChange={(v) => edit((l) => void (l[i].title = v), `${id}.${i}.title`)} />
          <Field label="Date" value={item.date} onChange={(v) => edit((l) => void (l[i].date = v), `${id}.${i}.date`)} />
          <Field label="Cadre" placeholder="En équipe" value={item.tag} onChange={(v) => edit((l) => void (l[i].tag = v), `${id}.${i}.tag`)} />
          <Field label="Lien" mono placeholder="https://github.com/…" value={item.link ?? ''} onChange={(v) => edit((l) => void (l[i].link = v || null), `${id}.${i}.link`)} />
          <Field className="col-span-2" multiline label="Description" placeholder={RICH_HINT} value={item.description} onChange={(v) => edit((l) => void (l[i].description = v), `${id}.${i}.description`)} />
        </div>
      )}
    </ItemList>
    <FromLibrary items={items} edit={edit} />
    </div>
  )
}

/** L'éditeur adapté au type de la section. */
export function SectionItems({ section, edit }: { section: Section; edit: EditItems<unknown> }) {
  const id = section.id
  switch (section.kind) {
    case 'education':
      return <EducationEditor id={id} items={section.items} edit={edit as EditItems<EducationItem>} />
    case 'skills':
      return <SkillsEditor id={id} items={section.items} edit={edit as EditItems<SkillGroup>} />
    case 'grid':
      return <GridEditor id={id} items={section.items} edit={edit as EditItems<GridItem>} />
    case 'languages':
      return <LanguagesEditor id={id} items={section.items} edit={edit as EditItems<Language>} />
    case 'bullets':
      return <BulletsEditor id={id} items={section.items} edit={edit as EditItems<string>} />
    case 'experience':
      return <ExperienceEditor id={id} items={section.items} edit={edit as EditItems<ExperienceItem>} />
    case 'projects':
      return <ProjectsEditor id={id} items={section.items} edit={edit as EditItems<ProjectItem>} />
  }
}

export const KIND_LABELS: Record<Section['kind'], string> = {
  education: 'Formation',
  skills: 'Compétences',
  grid: 'Grille',
  languages: 'Langues',
  bullets: 'Liste',
  experience: 'Expériences',
  projects: 'Projets',
}
