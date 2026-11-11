import { Check, ChevronDown, Download, Loader2, Lock, Plus, Search, Sparkles, Trash2, Wand2, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'

import { AutoTextarea, Field } from '@/components/editor/fields'
import { Segmented } from '@/components/style/controls'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useMe } from '@/hooks/use-me'
import { api } from '@/lib/api'
import { baseCVs } from '@/lib/bases'
import type { Library, LibraryExperience, LibraryProject, LibrarySkill, ProjectDraft, SkillLevel } from '@/lib/types'
import { cn } from '@/lib/utils'

const newId = (prefix: string) => `${prefix}-${crypto.randomUUID().slice(0, 8)}`
const message = (error: unknown) => (error instanceof Error ? error.message : String(error))
const fold = (text: string) => text.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase()

type Part = 'projects' | 'skills' | 'experiences'

/** La bibliothèque chargée, modifiée localement et enregistrée après une pause. */
function useLibrary() {
  const [library, setLibrary] = useState<Library | null>(null)
  const [saving, setSaving] = useState(false)
  const dirty = useRef<Record<Part, boolean>>({ projects: false, skills: false, experiences: false })
  const latest = useRef<Library | null>(null)

  useEffect(() => {
    api
      .getLibrary()
      .then((lib) => {
        latest.current = lib
        setLibrary(lib)
      })
      .catch((error: Error) => toast.error('Bibliothèque indisponible', { description: error.message }))
  }, [])

  const flush = useCallback(async () => {
    const lib = latest.current
    if (!lib) return
    setSaving(true)
    try {
      if (dirty.current.projects) {
        dirty.current.projects = false
        await api.saveProjects(lib.projects)
      }
      if (dirty.current.skills) {
        dirty.current.skills = false
        await api.saveSkills(lib.skills)
      }
      if (dirty.current.experiences) {
        dirty.current.experiences = false
        await api.saveExperiences(lib.experiences)
      }
    } catch (error) {
      toast.error("La bibliothèque n'a pas été enregistrée", { description: message(error) })
    } finally {
      setSaving(false)
    }
  }, [])

  const timer = useRef<number>(undefined)
  const change = useCallback(
    (part: Part, mutate: (lib: Library) => void) => {
      const current = latest.current
      if (!current) return
      const next = structuredClone(current)
      mutate(next)
      latest.current = next
      setLibrary(next)
      dirty.current[part] = true
      window.clearTimeout(timer.current)
      timer.current = window.setTimeout(() => void flush(), 500)
    },
    [flush],
  )
  useEffect(() => () => void flush(), [flush])

  const replace = (lib: Library) => {
    latest.current = lib
    setLibrary(lib)
  }
  // Avant une opération du serveur : les modifications locales d'abord.
  const settle = async () => {
    window.clearTimeout(timer.current)
    await flush()
  }
  return { library, saving, change, replace, settle }
}

export function LibraryPage() {
  const { library, saving, change, replace, settle } = useLibrary()
  const me = useMe()
  const [filling, setFilling] = useState(false)

  const fill = async () => {
    setFilling(true)
    try {
      await settle()
      const result = await api.fillLibrary()
      replace(result.library)
      const { projects, skills, experiences } = result.added
      toast.success(
        projects + skills + experiences
          ? `Ajoutés : ${projects} projet(s), ${skills} compétence(s), ${experiences} expérience(s)`
          : 'Rien de nouveau : tout est déjà dans la bibliothèque',
      )
      if (result.github_error) toast.warning('GitHub non lu', { description: result.github_error })
    } catch (error) {
      toast.error('Remplissage impossible', { description: message(error) })
    } finally {
      setFilling(false)
    }
  }

  const proposals = library
    ? library.projects.filter((p) => p.status === 'proposé').length + library.skills.filter((s) => s.status === 'proposé').length
    : 0

  return (
    <div className="flex h-full flex-col">
      <header className="flex h-11 shrink-0 items-center gap-3 border-b px-5">
        <h1 className="text-[13px] font-semibold tracking-tight">Bibliothèque</h1>
        {saving && <Loader2 className="size-3.5 animate-spin text-muted-foreground" aria-label="Enregistrement" />}
        {proposals > 0 && <Badge variant="secondary" className="h-5 text-[11px] font-normal">{proposals} à valider</Badge>}
        <Button size="sm" className="ml-auto h-8 gap-1.5 text-[12px]" disabled={filling || !library} onClick={() => void fill()}>
          {filling ? <Loader2 className="size-3.5 animate-spin" /> : <Download className="size-3.5" />}
          {/* En ligne, GitHub n'est pas lu : le compte de la machine serait celui de Yahya. */}
          {me?.mode === 'serveur' ? 'Remplir depuis mon CV' : 'Remplir depuis mon CV et GitHub'}
        </Button>
      </header>
      <Tabs defaultValue="skills" className="flex min-h-0 flex-1 flex-col gap-0">
        <div className="shrink-0 border-b px-5 py-2">
          <TabsList className="h-8">
            <TabsTrigger value="skills" className="px-3 text-[12px]">
              Compétences {library && <span className="ml-1 text-muted-foreground tabular-nums">{library.skills.length}</span>}
            </TabsTrigger>
            <TabsTrigger value="experiences" className="px-3 text-[12px]">
              Expériences {library && <span className="ml-1 text-muted-foreground tabular-nums">{library.experiences.length}</span>}
            </TabsTrigger>
            <TabsTrigger value="projects" className="px-3 text-[12px]">
              Projets {library && <span className="ml-1 text-muted-foreground tabular-nums">{library.projects.length}</span>}
            </TabsTrigger>
          </TabsList>
        </div>
        <TabsContent value="skills" className="min-h-0 flex-1">
          <ScrollArea className="h-full">
            <div className="mx-auto max-w-3xl px-6 py-6">
              {library ? <Skills library={library} change={change} replace={replace} settle={settle} /> : <Loading />}
            </div>
          </ScrollArea>
        </TabsContent>
        <TabsContent value="experiences" className="min-h-0 flex-1">
          <ScrollArea className="h-full">
            <div className="mx-auto max-w-3xl px-6 py-6">{library ? <Experiences library={library} change={change} /> : <Loading />}</div>
          </ScrollArea>
        </TabsContent>
        <TabsContent value="projects" className="min-h-0 flex-1">
          <ScrollArea className="h-full">
            <div className="mx-auto max-w-3xl px-6 py-6">{library ? <Projects library={library} change={change} /> : <Loading />}</div>
          </ScrollArea>
        </TabsContent>
      </Tabs>
    </div>
  )
}

function Loading() {
  return <div className="flex flex-col gap-3">{[0, 1, 2].map((i) => <div key={i} className="h-16 animate-pulse rounded-xl bg-muted" />)}</div>
}

type Change = ReturnType<typeof useLibrary>['change']

function SectionTitle({ title, count, children }: { title: string; count: number; children?: React.ReactNode }) {
  return (
    <div className="mb-2.5 flex items-center gap-2">
      <h2 className="text-[13px] font-semibold tracking-tight">{title}</h2>
      <span className="text-[12px] text-muted-foreground tabular-nums">{count}</span>
      <span className="ml-auto flex items-center gap-1">{children}</span>
    </div>
  )
}

function Empty({ text }: { text: string }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed px-6 py-10 text-center">
      <Sparkles className="size-5 text-muted-foreground" />
      <p className="max-w-sm text-[12.5px] text-muted-foreground">{text}</p>
    </div>
  )
}

const inputClass =
  'h-8 rounded-md border bg-background px-2.5 text-[12.5px] shadow-xs outline-none focus:border-ring focus:ring-[3px] focus:ring-ring/40'

// ─── Compétences ─────────────────────────────────────────────────────────────

const LEVELS: { value: SkillLevel; label: string }[] = [
  { value: 'notions', label: 'Notions' },
  { value: 'pratique', label: 'Pratique' },
  { value: 'maîtrise', label: 'Maîtrise' },
]

interface SkillsProps {
  library: Library
  change: Change
  replace: (lib: Library) => void
  settle: () => Promise<void>
}

function Skills({ library, change, replace, settle }: SkillsProps) {
  const proposed = library.skills.filter((s) => s.status === 'proposé')
  const validated = library.skills.filter((s) => s.status === 'validé')
  const categories = [...new Set(library.skills.map((s) => s.category))]
  const [text, setText] = useState('')
  const [category, setCategory] = useState('')
  const [level, setLevel] = useState<SkillLevel | ''>('')
  const [adding, setAdding] = useState(false)
  const [search, setSearch] = useState('')
  const [onlyOffers, setOnlyOffers] = useState(false)

  const shown = useMemo(() => {
    const needle = fold(search.trim())
    return validated.filter(
      (s) =>
        (!onlyOffers || s.source === 'offre') &&
        (!needle || fold([s.name, s.category, ...s.aliases, s.evidence].join(' ')).includes(needle)),
    )
  }, [validated, search, onlyOffers])
  const groups = [...new Set(shown.map((s) => s.category))]
  const fromOffers = validated.filter((s) => s.source === 'offre').length

  const edit = (id: string, mutate: (s: LibrarySkill) => void) =>
    change('skills', (lib) => {
      const target = lib.skills.find((s) => s.id === id)
      if (target) mutate(target)
    })
  const remove = (id: string) => change('skills', (lib) => void (lib.skills = lib.skills.filter((s) => s.id !== id)))

  const add = async () => {
    if (!text.trim()) return
    setAdding(true)
    try {
      await settle()
      const result = await api.addSkills(text, { category, level: level || null })
      replace(result.library)
      setText('')
      if (result.added.length) toast.success(`Ajoutée(s) : ${result.added.join(', ')}`)
      if (result.known.length) toast.info(`Déjà dans la bibliothèque : ${result.known.join(', ')}`)
    } catch (error) {
      toast.error('Ajout impossible', { description: message(error) })
    } finally {
      setAdding(false)
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <p className="text-[12.5px] text-muted-foreground">
        Tout ce qui est ici, l'IA peut le mettre dans tes CV sans te demander. Le reste, elle te le propose « à confirmer ».
        N'ajoute que ce que tu peux défendre en entretien.
      </p>

      {proposed.length > 0 && (
        <section>
          <SectionTitle title="À valider" count={proposed.length}>
            <Button
              variant="outline"
              size="sm"
              className="h-7 gap-1 px-2.5 text-[12px]"
              onClick={() => change('skills', (lib) => lib.skills.forEach((s) => void (s.status = 'validé')))}
            >
              <Check className="size-3.5" /> Tout valider
            </Button>
          </SectionTitle>
          <div className="flex flex-wrap gap-1.5">
            {proposed.map((skill) => (
              <span key={skill.id} className="flex items-center gap-0.5 rounded-lg border border-dashed bg-card py-0.5 pr-0.5 pl-2 text-[12.5px]">
                {skill.name}
                <button type="button" aria-label={`Valider ${skill.name}`} onClick={() => edit(skill.id, (s) => void (s.status = 'validé'))} className="ml-1 rounded-md p-1 text-success hover:bg-success/10"><Check className="size-3.5" /></button>
                <button type="button" aria-label={`Refuser ${skill.name}`} onClick={() => remove(skill.id)} className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"><X className="size-3.5" /></button>
              </span>
            ))}
          </div>
        </section>
      )}

      <section className="flex flex-col gap-2 rounded-xl border bg-card surface p-3.5">
        <h2 className="text-[13px] font-semibold tracking-tight">Ajouter des compétences</h2>
        <form className="flex flex-col gap-2" onSubmit={(e) => { e.preventDefault(); void add() }}>
          <AutoTextarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void add() }
            }}
            placeholder="Une ou plusieurs, séparées par des virgules : Kubernetes, Streamlit, dbt"
            aria-label="Compétences à ajouter"
          />
          <div className="flex flex-wrap items-center gap-2">
            <input value={category} onChange={(e) => setCategory(e.target.value)} placeholder="Catégorie (devinée si vide)" list="skill-categories" className={cn(inputClass, 'w-56')} />
            <datalist id="skill-categories">{categories.map((c) => <option key={c} value={c} />)}</datalist>
            <Segmented
              value={level as SkillLevel}
              onChange={(v) => setLevel(level === v ? '' : v)}
              options={LEVELS.map((l) => ({ ...l, title: 'Niveau (facultatif)' }))}
            />
            <Button type="submit" size="sm" className="ml-auto h-8 gap-1 text-[12px]" disabled={!text.trim() || adding}>
              {adding ? <Loader2 className="size-3.5 animate-spin" /> : <Plus className="size-3.5" />} Ajouter
            </Button>
          </div>
        </form>
      </section>

      <section>
        <SectionTitle title="Mes compétences" count={validated.length}>
          <span className="relative">
            <Search className="pointer-events-none absolute top-2 left-2 size-3.5 text-muted-foreground" />
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Rechercher" aria-label="Rechercher une compétence" className={cn(inputClass, 'h-7 w-40 pl-7')} />
          </span>
          {fromOffers > 0 && (
            <Button
              variant={onlyOffers ? 'secondary' : 'ghost'}
              size="sm"
              className="h-7 px-2 text-[12px]"
              aria-pressed={onlyOffers}
              onClick={() => setOnlyOffers(!onlyOffers)}
            >
              Ajoutées depuis une offre ({fromOffers})
            </Button>
          )}
        </SectionTitle>
        {validated.length === 0 ? (
          <Empty text="Aucune compétence. Clique « Remplir depuis mon CV… », ou ajoute-les ci-dessus." />
        ) : shown.length === 0 ? (
          <p className="text-[12.5px] text-muted-foreground">Aucune compétence ne correspond.</p>
        ) : (
          <div className="flex flex-col gap-4">
            {groups.map((group) => (
              <div key={group}>
                <p className="mb-1.5 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">{group}</p>
                <div className="flex flex-wrap gap-1.5">
                  {shown.filter((s) => s.category === group).map((skill) => (
                    <SkillChip key={skill.id} skill={skill} categories={categories} edit={(mutate) => edit(skill.id, mutate)} remove={() => remove(skill.id)} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

function SkillChip({ skill, categories, edit, remove }: { skill: LibrarySkill; categories: string[]; edit: (mutate: (s: LibrarySkill) => void) => void; remove: () => void }) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          title={skill.source === 'offre' ? 'Confirmée pendant un ciblage' : undefined}
          className={cn(
            'flex items-center gap-1 rounded-lg border bg-card px-2.5 py-1 text-[12.5px] shadow-xs transition-colors hover:border-ring/50 hover:bg-muted/40',
            skill.source === 'offre' && 'border-primary/40',
          )}
        >
          {skill.name}
          {skill.level && <span className="text-[11px] text-muted-foreground">· {skill.level}</span>}
          {skill.aliases.length > 0 && <span className="text-[11px] text-muted-foreground">+{skill.aliases.length}</span>}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80 p-3">
        <div className="flex flex-col gap-3">
          <Field label="Nom" value={skill.name} onChange={(v) => edit((s) => void (s.name = v))} />
          <label className="flex flex-col gap-1.5">
            <span className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">Catégorie</span>
            <input value={skill.category} list="skill-categories-chip" onChange={(e) => edit((s) => void (s.category = e.target.value))} className={inputClass} />
            <datalist id="skill-categories-chip">{categories.map((c) => <option key={c} value={c} />)}</datalist>
          </label>
          <div className="flex flex-col gap-1.5">
            <span className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">Niveau</span>
            <Segmented
              value={(skill.level ?? '') as SkillLevel}
              onChange={(v) => edit((s) => void (s.level = s.level === v ? null : v))}
              options={LEVELS}
            />
          </div>
          <Field label="Où (stage, projet, cours…)" placeholder="ex. stage chez Logistica, projet TrafficLens" value={skill.evidence} onChange={(v) => edit((s) => void (s.evidence = v))} />
          <div className="flex flex-col gap-1.5">
            <span className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">Autres écritures (pour les offres)</span>
            <TagInput values={skill.aliases} onChange={(aliases) => edit((s) => void (s.aliases = aliases))} placeholder="ex. JS, ECMAScript" />
          </div>
          <Button variant="ghost" size="sm" className="h-7 self-start px-2 text-[12px] text-destructive" onClick={remove}><Trash2 className="size-3.5" /> Supprimer</Button>
        </div>
      </PopoverContent>
    </Popover>
  )
}

function TagInput({ values, onChange, placeholder }: { values: string[]; onChange: (values: string[]) => void; placeholder: string }) {
  const [draft, setDraft] = useState('')
  const commit = () => {
    const parts = draft.split(',').map((p) => p.trim()).filter(Boolean)
    if (parts.length) onChange([...values, ...parts.filter((p) => !values.includes(p))])
    setDraft('')
  }
  return (
    <div className="flex min-h-9 flex-wrap items-center gap-1 rounded-md border bg-background px-1.5 py-1 shadow-xs focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/40">
      {values.map((value) => (
        <span key={value} className="flex items-center gap-0.5 rounded bg-muted py-0.5 pr-0.5 pl-1.5 text-[12px]">
          {value}
          <button type="button" aria-label={`Retirer ${value}`} onClick={() => onChange(values.filter((v) => v !== value))} className="rounded p-0.5 text-muted-foreground hover:bg-background hover:text-foreground"><X className="size-3" /></button>
        </span>
      ))}
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); commit() }
          if (e.key === 'Backspace' && !draft && values.length) onChange(values.slice(0, -1))
        }}
        onBlur={commit}
        placeholder={values.length ? '' : placeholder}
        className="min-w-24 flex-1 bg-transparent px-1 text-[12.5px] outline-none placeholder:text-muted-foreground"
      />
    </div>
  )
}

// ─── Expériences ─────────────────────────────────────────────────────────────

function Experiences({ library, change }: { library: Library; change: Change }) {
  // Les puces des CV classiques, pour les signaler dans les réserves.
  const [onCv, setOnCv] = useState<Set<string>>(new Set())
  useEffect(() => {
    api
      .listCVs()
      .then((all) => Promise.all(baseCVs(all).map((cv) => api.getCV(cv.slug))))
      .then(
        (bases) => setOnCv(new Set(bases.flatMap((cv) => cv.content.sections.flatMap((s) => (s.kind === 'experience' ? s.items.flatMap((i) => i.bullets) : []))))),
        () => undefined,
      )
  }, [])
  const edit = (id: string, mutate: (e: LibraryExperience) => void) =>
    change('experiences', (lib) => {
      const target = lib.experiences.find((e) => e.id === id)
      if (target) mutate(target)
    })
  const add = () =>
    change('experiences', (lib) => void lib.experiences.push({ id: newId('experience'), title: 'Nouvelle expérience', place: '', dates: '', bullets: [''], source: 'manuel', status: 'validé' }))

  return (
    <div className="flex flex-col gap-5">
      <p className="text-[12.5px] text-muted-foreground">
        La réserve de chaque expérience : écris toutes les puces vraies, pas seulement celles du CV. À chaque offre, l'IA
        choisit les plus utiles, autant que sur ton CV. Le titre doit être celui du CV pour que les deux se retrouvent.
      </p>
      <SectionTitle title="Mes expériences" count={library.experiences.length}>
        <Button variant="ghost" size="sm" className="h-7 gap-1 px-2 text-[12px]" onClick={add}><Plus className="size-3.5" /> Expérience</Button>
      </SectionTitle>
      {library.experiences.length === 0 && <Empty text="Aucune expérience. Clique « Remplir depuis mon CV… » pour reprendre celles de ton CV." />}
      {library.experiences.map((experience) => (
        <article key={experience.id} className="flex flex-col gap-3 rounded-xl border bg-card surface p-3.5">
          <div className="grid grid-cols-[1fr_1fr_auto] items-end gap-2">
            <Field label="Titre (comme dans le CV)" value={experience.title} onChange={(v) => edit(experience.id, (e) => void (e.title = v))} />
            <Field label="Lieu" value={experience.place} onChange={(v) => edit(experience.id, (e) => void (e.place = v))} />
            <Button
              variant="ghost"
              size="icon"
              className="size-8 text-muted-foreground"
              aria-label={`Supprimer ${experience.title}`}
              onClick={() => change('experiences', (lib) => void (lib.experiences = lib.experiences.filter((e) => e.id !== experience.id)))}
            >
              <Trash2 className="size-3.5" />
            </Button>
          </div>
          <div className="flex flex-col gap-1.5">
            <span className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
              Puces ({experience.bullets.length})
            </span>
            {experience.bullets.map((bullet, i) => (
              <div key={i} className="group/b flex items-start gap-1.5">
                <span className="mt-2.5 size-1 shrink-0 rounded-full bg-muted-foreground/60" />
                <AutoTextarea value={bullet} onChange={(e) => edit(experience.id, (x) => void (x.bullets[i] = e.target.value))} aria-label={`Puce ${i + 1} de ${experience.title}`} />
                {onCv.has(bullet) && <Badge variant="outline" className="mt-1.5 h-5 shrink-0 text-[10px] font-normal">sur le CV</Badge>}
                <Button variant="ghost" size="icon" className="size-7 shrink-0 text-muted-foreground opacity-0 group-hover/b:opacity-100 focus-visible:opacity-100" aria-label="Supprimer la puce" onClick={() => edit(experience.id, (x) => void x.bullets.splice(i, 1))}><Trash2 className="size-3.5" /></Button>
              </div>
            ))}
            <Button variant="ghost" size="sm" className="h-7 self-start px-2 text-[12px] text-muted-foreground" onClick={() => edit(experience.id, (x) => void x.bullets.push(''))}>
              <Plus className="size-3.5" /> Puce
            </Button>
          </div>
        </article>
      ))}
    </div>
  )
}

// ─── Projets ─────────────────────────────────────────────────────────────────

const SOURCE_LABEL = { cv: 'du CV', github: 'de GitHub', manuel: 'ajouté à la main', offre: "d'une offre" } as const

function Projects({ library, change }: { library: Library; change: Change }) {
  const proposed = library.projects.filter((p) => p.status === 'proposé')
  const validated = library.projects.filter((p) => p.status === 'validé')
  const [open, setOpen] = useState<string | null>(null)
  const edit = (id: string, mutate: (p: LibraryProject) => void) =>
    change('projects', (lib) => {
      const target = lib.projects.find((p) => p.id === id)
      if (target) mutate(target)
    })
  const remove = (id: string) => change('projects', (lib) => void (lib.projects = lib.projects.filter((p) => p.id !== id)))
  const add = () => {
    const id = newId('projet')
    change('projects', (lib) => void lib.projects.unshift({ id, title: 'Nouveau projet', date: '', context: null, team: null, techs: [], description: '', bullets: [], link: null, private: false, notes: '', source: 'manuel', status: 'validé' }))
    setOpen(id)
  }

  return (
    <div className="flex flex-col gap-8">
      {proposed.length > 0 && (
        <section>
          <SectionTitle title="À valider" count={proposed.length}>
            <Button
              variant="outline"
              size="sm"
              className="h-7 gap-1 px-2.5 text-[12px]"
              onClick={() => change('projects', (lib) => lib.projects.forEach((p) => void (p.status = 'validé')))}
            >
              <Check className="size-3.5" /> Tout valider
            </Button>
          </SectionTitle>
          <div className="flex flex-col gap-2.5">
            {proposed.map((project) => (
              <ProjectCard
                key={project.id}
                project={project}
                open={open === project.id}
                onToggle={() => setOpen(open === project.id ? null : project.id)}
                edit={(mutate) => edit(project.id, mutate)}
                actions={
                  <>
                    <Button size="sm" className="h-7 gap-1 px-2.5 text-[12px]" onClick={() => edit(project.id, (p) => void (p.status = 'validé'))}><Check className="size-3.5" /> Valider</Button>
                    <Button variant="ghost" size="sm" className="h-7 gap-1 px-2 text-[12px] text-muted-foreground" onClick={() => remove(project.id)}><X className="size-3.5" /> Refuser</Button>
                  </>
                }
              />
            ))}
          </div>
        </section>
      )}
      <section>
        <SectionTitle title="Mes projets" count={validated.length}>
          <Button variant="ghost" size="sm" className="h-7 gap-1 px-2 text-[12px]" onClick={add}><Plus className="size-3.5" /> Projet</Button>
        </SectionTitle>
        {validated.length === 0 ? (
          <Empty text="Aucun projet validé. Clique « Remplir depuis mon CV… », ou ajoute-en un." />
        ) : (
          <div className="flex flex-col gap-2">
            {validated.map((project) => (
              <ProjectCard
                key={project.id}
                project={project}
                open={open === project.id}
                onToggle={() => setOpen(open === project.id ? null : project.id)}
                edit={(mutate) => edit(project.id, mutate)}
                actions={<Button variant="ghost" size="icon" className="size-7 text-muted-foreground" aria-label={`Supprimer ${project.title}`} onClick={() => remove(project.id)}><Trash2 className="size-3.5" /></Button>}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

const TEAM_LABEL = { seul: 'Seul', binôme: 'En binôme', équipe: 'En équipe' } as const

function ProjectCard({ project, open, onToggle, edit, actions }: { project: LibraryProject; open: boolean; onToggle: () => void; edit: (mutate: (p: LibraryProject) => void) => void; actions: React.ReactNode }) {
  const summary = project.description || project.notes
  const [drafting, setDrafting] = useState(false)
  const [draft, setDraft] = useState<ProjectDraft | null>(null)
  const canDraft = Boolean(project.notes || project.description || project.bullets.length)

  const write = async () => {
    setDrafting(true)
    try {
      setDraft(await api.draftProject(project.id))
    } catch (error) {
      toast.error('Rédaction impossible', { description: message(error) })
    } finally {
      setDrafting(false)
    }
  }

  return (
    <div className={cn('rounded-xl border bg-card surface transition-shadow', open && 'shadow-md')}>
      <div className="flex items-start gap-3 p-3.5">
        <button type="button" onClick={onToggle} className="min-w-0 flex-1 text-left" aria-expanded={open}>
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-[13.5px] font-semibold tracking-tight">{project.title}</span>
            {project.date && <span className="text-[12px] text-muted-foreground tabular-nums">{project.date}</span>}
            {project.team ? (
              <Badge variant="secondary" className="h-5 text-[10.5px] font-normal">{TEAM_LABEL[project.team]}</Badge>
            ) : (
              <Badge variant="outline" className="h-5 border-warning/50 text-[10.5px] font-normal text-warning">Cadre à préciser</Badge>
            )}
            {project.context && <Badge variant="outline" className="h-5 text-[10.5px] font-normal">{project.context}</Badge>}
            {project.private && <Badge variant="outline" className="h-5 gap-1 text-[10.5px] font-normal text-warning"><Lock className="size-2.5" /> dépôt privé</Badge>}
          </p>
          {summary && <p className={cn('mt-1 text-[12.5px] text-muted-foreground', !open && 'line-clamp-2')}>{summary}</p>}
          {project.techs.length > 0 && (
            <p className="mt-2 flex flex-wrap gap-1">
              {project.techs.map((t) => <span key={t} className="rounded-md bg-muted px-1.5 py-0.5 text-[11px]">{t}</span>)}
            </p>
          )}
          {project.status === 'proposé' && <p className="mt-1.5 text-[11px] text-muted-foreground/80">Proposé {SOURCE_LABEL[project.source]}</p>}
        </button>
        <div className="flex shrink-0 items-center gap-1">
          {actions}
          <Button variant="ghost" size="icon" className="size-7 text-muted-foreground" onClick={onToggle} aria-label={open ? 'Replier' : 'Modifier'}>
            <ChevronDown className={cn('size-4 transition-transform', open && 'rotate-180')} />
          </Button>
        </div>
      </div>
      {open && (
        <div className="grid grid-cols-2 gap-3 border-t px-3.5 pt-3 pb-4">
          <div className="col-span-2 flex items-center gap-2">
            <Button variant="outline" size="sm" className="h-7 gap-1.5 text-[12px]" disabled={!canDraft || drafting} onClick={() => void write()}>
              {drafting ? <Loader2 className="size-3.5 animate-spin" /> : <Wand2 className="size-3.5" />} Rédiger avec l'IA
            </Button>
            <span className="text-[11.5px] text-muted-foreground">
              {canDraft ? 'Description, points et technos tirés des notes (README). 1 requête.' : 'Ajoute des notes (README) ou une description d’abord.'}
            </span>
          </div>
          {draft && (
            <div className="col-span-2 flex flex-col gap-2 rounded-lg border border-primary/30 bg-primary/5 p-3">
              <p className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">Proposition de l'IA</p>
              <p className="text-[12.5px]">{draft.description}</p>
              <ul className="flex list-disc flex-col gap-0.5 pl-4 text-[12.5px]">{draft.bullets.map((b) => <li key={b}>{b}</li>)}</ul>
              <p className="flex flex-wrap gap-1">{draft.techs.map((t) => <span key={t} className="rounded-md bg-background px-1.5 py-0.5 text-[11px]">{t}</span>)}</p>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  className="h-7 gap-1 text-[12px]"
                  onClick={() => {
                    edit((p) => {
                      p.description = draft.description
                      p.bullets = draft.bullets
                      p.techs = [...new Set([...p.techs, ...draft.techs])]
                    })
                    setDraft(null)
                  }}
                >
                  <Check className="size-3.5" /> Utiliser
                </Button>
                <Button variant="ghost" size="sm" className="h-7 text-[12px] text-muted-foreground" onClick={() => setDraft(null)}>Ignorer</Button>
              </div>
            </div>
          )}
          <Field className="col-span-2" label="Titre (comme dans le CV)" value={project.title} onChange={(v) => edit((p) => void (p.title = v))} />
          <Field label="Date" placeholder="2026, ou Mars – Mai 2026" value={project.date} onChange={(v) => edit((p) => void (p.date = v))} />
          <Field label="Lien" mono placeholder="https://github.com/…" value={project.link ?? ''} onChange={(v) => edit((p) => void (p.link = v || null))} />
          <div className="flex flex-col gap-1.5">
            <span className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">Contexte</span>
            <Segmented value={project.context ?? 'autre'} onChange={(v) => edit((p) => void (p.context = v))} options={[{ value: 'école', label: 'École' }, { value: 'stage', label: 'Stage' }, { value: 'perso', label: 'Perso' }, { value: 'autre', label: 'Autre' }]} />
          </div>
          <div className="flex flex-col gap-1.5">
            <span className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">Cadre</span>
            {/* Rien de sélectionné tant que le cadre n'est pas précisé. */}
            <Segmented value={project.team ?? ('' as 'seul')} onChange={(v) => edit((p) => void (p.team = v))} options={[{ value: 'seul', label: 'Seul' }, { value: 'binôme', label: 'Binôme' }, { value: 'équipe', label: 'Équipe' }]} />
          </div>
          <div className="col-span-2 flex flex-col gap-1.5">
            <span className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">Technologies</span>
            <TagInput values={project.techs} onChange={(techs) => edit((p) => void (p.techs = techs))} placeholder="Python, Docker… puis Entrée" />
          </div>
          <Field className="col-span-2" multiline label="Description (la phrase du CV)" placeholder="**gras** et __italique__" value={project.description} onChange={(v) => edit((p) => void (p.description = v))} />
          <div className="col-span-2 flex flex-col gap-1.5">
            <span className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">Points détaillés</span>
            {project.bullets.map((bullet, i) => (
              <div key={i} className="group/b flex items-start gap-1">
                <AutoTextarea value={bullet} onChange={(e) => edit((p) => void (p.bullets[i] = e.target.value))} />
                <Button variant="ghost" size="icon" className="size-7 shrink-0 text-muted-foreground opacity-0 group-hover/b:opacity-100" aria-label="Supprimer le point" onClick={() => edit((p) => void p.bullets.splice(i, 1))}><Trash2 className="size-3.5" /></Button>
              </div>
            ))}
            <Button variant="ghost" size="sm" className="h-7 self-start px-2 text-[12px] text-muted-foreground" onClick={() => edit((p) => void p.bullets.push(''))}><Plus className="size-3.5" /> Point</Button>
          </div>
          <Field className="col-span-2" multiline label="Notes pour l'IA (README, contexte, chiffres…)" value={project.notes} onChange={(v) => edit((p) => void (p.notes = v))} />
        </div>
      )}
    </div>
  )
}
