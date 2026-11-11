import { Plus, Sparkles, TriangleAlert } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { CvEditor } from '@/hooks/use-cv-editor'
import { api } from '@/lib/api'
import type { CVContent, OfferInfo, PageLocation, Section } from '@/lib/types'
import { at } from '@/lib/focus'
import { cn } from '@/lib/utils'

// Les mots-clés absents montrés dans la bande ; les autres sont dans l'onglet Offre.
const SHOWN = 5

interface ScoreBandProps {
  slug: string
  pdfVersion: number | null
  content: CVContent | null
  update: CvEditor['update']
  // Mode manuel : le contenu ne se modifie plus d'ici.
  locked: boolean
  onReveal: (location: PageLocation) => void
  onOffer: () => void
}

/** Sous l'en-tête d'un CV ciblé : sa correspondance à l'offre et les mots-clés qui manquent. */
export function ScoreBand({ slug, pdfVersion, content, update, locked, onReveal, onOffer }: ScoreBandProps) {
  const [info, setInfo] = useState<OfferInfo | null>(null)

  // Le score est mesuré sur le PDF : relu à chaque compilation.
  useEffect(() => {
    let cancelled = false
    api.getOffer(slug).then(
      (found) => !cancelled && setInfo(found),
      () => !cancelled && setInfo(null),
    )
    return () => {
      cancelled = true
    }
  }, [slug, pdfVersion])

  if (!info?.score) return null
  const { score } = info
  const weight = new Map(info.analysis.keywords.map((k) => [k.term, k.importance]))
  const absent = [...score.absent].sort((a, b) => (weight.get(b) ?? 1) - (weight.get(a) ?? 1))
  const lacking = new Map(info.missing.map((m) => [m.term.toLocaleLowerCase('fr'), m.note]))
  const categories = new Map(info.analysis.keywords.map((k) => [k.term.toLocaleLowerCase('fr'), k.category]))
  const tone = score.score >= 70 ? 'text-success' : score.score >= 45 ? 'text-warning' : 'text-destructive'
  const bar = score.score >= 70 ? 'bg-success' : score.score >= 45 ? 'bg-warning' : 'bg-destructive'

  return (
    <div role="region" aria-label="Correspondance à l'offre" className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1.5 border-b bg-muted/40 px-4 py-2">
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="flex cursor-default items-center gap-2">
            <span className="text-[12px] text-muted-foreground">Correspondance à l'offre</span>
            <span className={cn('font-mono text-[14px] font-semibold tabular-nums', tone)}>{score.score} %</span>
            <span className="h-1.5 w-16 overflow-hidden rounded-full bg-border">
              <span className={cn('block h-full rounded-full transition-[width] duration-500', bar)} style={{ width: `${score.score}%` }} />
            </span>
          </span>
        </TooltipTrigger>
        <TooltipContent className="max-w-64">
          Part des mots-clés de l'offre, pondérés par leur importance, trouvés dans le texte du PDF. Recalculée à chaque compilation.
        </TooltipContent>
      </Tooltip>
      <span aria-hidden className="h-4 w-px bg-border" />
      {absent.length === 0 ? (
        <span className="text-[12px] text-muted-foreground">Tous les mots-clés de l'offre sont dans le CV.</span>
      ) : (
        <>
          <span className="text-[12px] text-muted-foreground">Absents du CV :</span>
          {absent.slice(0, SHOWN).map((term) =>
            locked || !content ? (
              <span key={term} className="rounded-full border border-dashed px-2 py-0.5 text-[11.5px] text-muted-foreground">
                {term}
              </span>
            ) : (
              <AddKeyword
                key={term}
                term={term}
                lacking={lacking.has(term.toLocaleLowerCase('fr'))}
                note={lacking.get(term.toLocaleLowerCase('fr')) ?? null}
                category={categories.get(term.toLocaleLowerCase('fr')) ?? null}
                content={content}
                update={update}
                onReveal={onReveal}
              />
            ),
          )}
          {absent.length > SHOWN && (
            <button type="button" onClick={onOffer} className="text-[12px] text-muted-foreground hover:text-foreground">
              +{absent.length - SHOWN} autre{absent.length - SHOWN > 1 ? 's' : ''}
            </button>
          )}
        </>
      )}
      <button type="button" onClick={onOffer} className="ml-auto text-[12px] font-medium text-primary hover:underline">
        Voir l'offre
      </button>
    </div>
  )
}

/** « Python, SQL. » + « Docker » → « Python, SQL, Docker. » */
function appendTerm(text: string, term: string): string {
  const trimmed = text.trimEnd()
  if (!trimmed) return term
  const end = /[.;]$/.test(trimmed) ? trimmed.slice(-1) : ''
  return `${end ? trimmed.slice(0, -1) : trimmed}, ${term}${end}`
}

const capital = (term: string) => term.charAt(0).toLocaleUpperCase('fr') + term.slice(1)
const plain = (text: string) => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()

const LANGUAGES = new Set(
  (
    'anglais francais allemand espagnol italien portugais neerlandais arabe chinois mandarin japonais russe coreen turc ' +
    'polonais suedois norvegien danois grec hebreu hindi roumain ukrainien vietnamien english french german spanish ' +
    'italian portuguese dutch arabic chinese japanese russian korean turkish polish swedish'
  ).split(' '),
)
const isLanguage = (term: string) => LANGUAGES.has(plain(term).split(/[\s(,-]/)[0])
// Une rubrique de savoir-être, à son titre.
const SOFT_TITLE = /soft|savoir|qualit|atout|personal|interpersonnel/i

// Où un mot-clé peut aller : un groupe de compétences, ou une nouvelle entrée d'une rubrique.
type Target =
  | { kind: 'group'; section: Section; index: number; label: string; text: string }
  | { kind: 'newgroup'; section: Section; label: string }
  | { kind: 'grid' | 'bullets' | 'languages'; section: Section }

const ENTRY: Record<'grid' | 'bullets' | 'languages', string> = { grid: 'nouvelle case', bullets: 'nouvelle ligne', languages: 'nouvelle langue' }

function targetName(target: Target): string {
  if (target.kind === 'group') return target.label || 'Groupe sans titre'
  if (target.kind === 'newgroup') return `Nouveau groupe « ${target.label} »`
  return target.section.title
}

/** La rubrique la plus logique pour ce mot, et pourquoi ; null si rien ne s'impose. */
function suggest(term: string, category: string | null, sections: Section[], group: { group: string | null; exists: boolean } | null) {
  const visible = (s: Section) => s.visible !== false
  if (isLanguage(term)) {
    const section = sections.find((s) => s.kind === 'languages' && visible(s)) ?? sections.find((s) => s.kind === 'languages')
    if (section) return { target: { kind: 'languages', section } as Target, why: `« ${term} » est une langue : ajoute ton niveau ensuite.` }
  }
  if (category === 'soft skill') {
    const soft = sections.filter((s) => (s.kind === 'grid' || s.kind === 'bullets') && SOFT_TITLE.test(s.title))
    const section = soft.find((s) => s.kind === 'grid') ?? soft[0] ?? sections.find((s) => s.kind === 'grid')
    if (section) return { target: { kind: section.kind as 'grid' | 'bullets', section } as Target, why: `L'offre range « ${term} » dans les savoir-être.` }
  }
  if (group?.group) {
    const section = sections.find((s) => s.kind === 'skills')
    if (section?.kind === 'skills') {
      const index = section.items.findIndex((g) => g.label === group.group)
      if (index >= 0) {
        const item = section.items[index]
        return { target: { kind: 'group', section, index, label: item.label, text: item.text } as Target, why: `« ${term} » se range d'habitude avec « ${item.label} ».` }
      }
      return { target: { kind: 'newgroup', section, label: group.group } as Target, why: `« ${term} » se range d'habitude dans un groupe « ${group.group} ».` }
    }
  }
  return null
}

interface AddKeywordProps {
  term: string
  // L'analyse de l'offre l'a rangé dans ce que la personne n'a pas.
  lacking: boolean
  note: string | null
  // Sa catégorie dans l'analyse de l'offre (« soft skill », « outil »…).
  category: string | null
  content: CVContent
  update: CvEditor['update']
  onReveal: (location: PageLocation) => void
}

function AddKeyword({ term, lacking, note, category, content, update, onReveal }: AddKeywordProps) {
  const [open, setOpen] = useState(false)
  const [group, setGroup] = useState<{ group: string | null; exists: boolean } | null>(null)
  const [naming, setNaming] = useState<{ sectionId: string; name: string } | null>(null)
  const sections = content.sections.filter((s) => ['skills', 'grid', 'bullets', 'languages'].includes(s.kind))
  const skillLabels = sections.flatMap((s) => (s.kind === 'skills' ? s.items.map((g) => g.label) : []))

  // À l'ouverture : le groupe où ce mot va d'habitude (dictionnaire de la bibliothèque, sans IA).
  const labelsKey = skillLabels.join('\n')
  useEffect(() => {
    if (!open || category === 'soft skill') return
    let live = true
    api.skillGroup(term, labelsKey ? labelsKey.split('\n') : []).then(
      (found) => live && setGroup(found),
      () => undefined,
    )
    return () => {
      live = false
    }
  }, [open, term, category, labelsKey])

  const best = suggest(term, category, sections, group)

  const add = (target: Target) => {
    let index = 0
    update((draft) => {
      const section = draft.sections.find((s) => s.id === target.section.id)
      if (!section) return
      section.visible = true
      if (target.kind === 'group' && section.kind === 'skills' && section.items[target.index]) {
        section.items[target.index].text = appendTerm(section.items[target.index].text, term)
        index = target.index
      } else if (target.kind === 'newgroup' && section.kind === 'skills') {
        index = section.items.push({ label: target.label, text: `${term}.` }) - 1
      } else if (target.kind === 'grid' && section.kind === 'grid') {
        const text = capital(term)
        index = section.items.push({ text, wide: text.length > 22 }) - 1
      } else if (target.kind === 'bullets' && section.kind === 'bullets') {
        index = section.items.push(capital(term)) - 1
      } else if (target.kind === 'languages' && section.kind === 'languages') {
        index = section.items.push({ name: capital(term), level: '' }) - 1
      }
    })
    setOpen(false)
    setNaming(null)
    onReveal(at(target.section.id, index))
    toast.success(`« ${term} » ajouté à « ${targetName(target)} »`, { description: 'Le score se met à jour à la prochaine compilation.' })
  }

  const dest = (target: Target, label: React.ReactNode, sub: string | null, key: string, suggested = false) => (
    <button
      key={key}
      type="button"
      onClick={() => add(target)}
      className={cn(
        'flex items-center justify-between gap-2 rounded-md border px-2 py-1.5 text-left text-[12.5px] transition-colors hover:bg-accent',
        suggested && 'border-primary/50 bg-accent',
      )}
    >
      <span className="min-w-0 truncate">
        {label}
        {sub && <span className="text-[11.5px] text-muted-foreground"> · {sub}</span>}
      </span>
      {suggested ? <span className="shrink-0 text-[10.5px] font-bold tracking-wide text-primary uppercase">Ajouter</span> : <Plus className="size-3.5 shrink-0 text-muted-foreground" />}
    </button>
  )

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) setNaming(null)
      }}
    >
      <PopoverTrigger asChild>
        <button
          type="button"
          className="flex items-center gap-0.5 rounded-full border border-dashed border-primary/40 bg-background px-2 py-0.5 text-[11.5px] font-medium text-primary transition-colors hover:bg-accent"
        >
          <Plus className="size-3" />
          {term}
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        className="flex max-h-[min(34rem,75vh)] w-80 flex-col gap-3 overflow-y-auto p-3"
        // Le curseur va dans le champ de la rubrique, pas sur le mot-clé.
        onCloseAutoFocus={(event) => event.preventDefault()}
      >
        <p className="text-[13px] font-medium">« {term} » n'est pas dans le PDF</p>
        {lacking ? (
          <p className="flex gap-1.5 rounded-md bg-status-interview-soft px-2 py-1.5 text-[12px] text-status-interview">
            <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
            <span>
              L'analyse de l'offre l'a rangé dans ce que tu n'as pas{note ? ` (${note})` : ''}. Ne l'ajoute que si c'est faux.
            </span>
          </p>
        ) : (
          <p className="text-[12px] text-muted-foreground">Ajoute-le seulement si c'est vrai : il te sera demandé en entretien.</p>
        )}
        {best && (
          <div className="flex flex-col gap-1">
            <p className="flex items-center gap-1 text-[10.5px] font-bold tracking-wider text-muted-foreground uppercase">
              <Sparkles className="size-3" /> Suggéré
            </p>
            {dest(best.target, targetName(best.target), best.target.kind === 'group' || best.target.kind === 'newgroup' ? null : ENTRY[best.target.kind], 'best', true)}
            <p className="rounded-md bg-muted px-2 py-1 text-[11.5px] text-muted-foreground">{best.why}</p>
          </div>
        )}
        {sections.length === 0 && (
          <p className="text-[12px] text-muted-foreground">Ce CV n'a aucune rubrique où ranger un mot : ajoute-en une dans l'onglet Contenu.</p>
        )}
        {sections.map((section) => (
          <div key={section.id} className="flex flex-col gap-1">
            <p className="text-[10.5px] font-bold tracking-wider text-muted-foreground uppercase">
              {section.title}
              <span className="font-medium tracking-normal normal-case">
                {section.kind === 'skills' ? ' · dans un groupe' : ` · ${ENTRY[section.kind as 'grid' | 'bullets' | 'languages']}`}
                {section.visible === false && ' · masquée'}
              </span>
            </p>
            {section.kind === 'skills' ? (
              <>
                {section.items.map((item, index) =>
                  dest({ kind: 'group', section, index, label: item.label, text: item.text }, item.label || 'Groupe sans titre', item.text.slice(0, 32), `${section.id}/${index}`),
                )}
                {naming?.sectionId === section.id ? (
                  <form
                    className="flex gap-1.5"
                    onSubmit={(event) => {
                      event.preventDefault()
                      if (naming.name.trim()) add({ kind: 'newgroup', section, label: naming.name.trim() })
                    }}
                  >
                    <input
                      autoFocus
                      value={naming.name}
                      onChange={(event) => setNaming({ sectionId: section.id, name: event.target.value })}
                      aria-label="Nom du nouveau groupe"
                      className="h-8 min-w-0 flex-1 rounded-md border bg-background px-2 text-[12.5px]"
                    />
                    <button type="submit" className="h-8 rounded-md bg-primary px-2.5 text-[12px] font-semibold text-primary-foreground">
                      Créer
                    </button>
                  </form>
                ) : (
                  <button
                    type="button"
                    onClick={() => setNaming({ sectionId: section.id, name: group?.group && !group.exists ? group.group : category === 'soft skill' ? 'Savoir-être' : '' })}
                    className="flex items-center justify-between gap-2 rounded-md border border-dashed px-2 py-1.5 text-left text-[12.5px] text-muted-foreground transition-colors hover:bg-accent"
                  >
                    Nouveau groupe…
                    <Plus className="size-3.5 shrink-0" />
                  </button>
                )}
              </>
            ) : (
              dest({ kind: section.kind as 'grid' | 'bullets' | 'languages', section }, capital(ENTRY[section.kind as 'grid' | 'bullets' | 'languages']), null, section.id)
            )}
          </div>
        ))}
      </PopoverContent>
    </Popover>
  )
}
