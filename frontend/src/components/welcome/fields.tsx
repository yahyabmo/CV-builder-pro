import { CheckCircle2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import type { ApplyBaseResult, CVContent, Section } from '@/lib/types'
import type { WelcomeIntent } from '@/lib/welcome-intent'

export type Kind = Section['kind']
type Item = Section['items'][number]

interface Field {
  key: string
  label: string
  // Une liste de textes (les puces), saisie une par ligne.
  lines?: boolean
  multiline?: boolean
  placeholder?: string
  wide?: boolean
}

/** Les champs d'un élément, selon le type de rubrique. */
export const FIELDS: Record<Kind, Field[]> = {
  education: [
    { key: 'title', label: 'Diplôme ou formation', placeholder: "ex. Diplôme d'ingénieur, Informatique" },
    { key: 'place', label: 'Établissement et ville' },
    { key: 'dates', label: 'Dates', placeholder: 'ex. 2024 – 2027' },
    { key: 'description', label: 'Précision, facultative', multiline: true, wide: true },
  ],
  experience: [
    { key: 'title', label: 'Intitulé', placeholder: 'ex. Stage Data Scientist' },
    { key: 'place', label: 'Entreprise et lieu' },
    { key: 'dates', label: 'Dates', placeholder: 'ex. Juin 2026 – Août 2026' },
    { key: 'tag', label: 'Précision, facultative', placeholder: 'ex. Équipe de trois' },
    { key: 'bullets', label: 'Ce que tu y as fait, une puce par ligne', lines: true, wide: true },
  ],
  projects: [
    { key: 'title', label: 'Nom du projet' },
    { key: 'tag', label: 'Cadre, facultatif', placeholder: 'ex. Projet personnel, En binôme' },
    { key: 'date', label: 'Date', placeholder: 'ex. 2026' },
    { key: 'link', label: 'Lien, facultatif', placeholder: 'https://github.com/…' },
    { key: 'description', label: 'Description', multiline: true, wide: true },
    { key: 'bullets', label: 'Puces, une par ligne (facultatif)', lines: true, wide: true },
  ],
  skills: [
    { key: 'label', label: 'Groupe', placeholder: 'ex. Programmation' },
    { key: 'text', label: 'Compétences, séparées par des virgules', placeholder: 'ex. Python, SQL, Docker.', wide: true },
  ],
  languages: [
    { key: 'name', label: 'Langue' },
    { key: 'level', label: 'Niveau', placeholder: 'ex. courant (C1)' },
  ],
  grid: [{ key: 'text', label: 'Qualité', wide: true }],
  bullets: [],
}

export function blankItem(kind: Kind): Item {
  switch (kind) {
    case 'education':
      return { title: '', place: '', dates: '', description: '' }
    case 'experience':
      return { title: '', tag: '', place: '', dates: '', bullets: [] }
    case 'projects':
      return { title: '', tag: '', date: '', description: '', bullets: [], link: null }
    case 'skills':
      return { label: '', text: '' }
    case 'languages':
      return { name: '', level: '' }
    case 'grid':
      return { text: '', wide: false }
    case 'bullets':
      return ''
  }
}

/** Un élément en deux lignes : son titre et ce qui le précise. */
export function summary(kind: Kind, item: Item): { title: string; detail: string } {
  if (typeof item === 'string') return { title: item, detail: '' }
  const value = item as unknown as Record<string, unknown>
  const text = (key: string) => (typeof value[key] === 'string' ? (value[key] as string) : '')
  switch (kind) {
    case 'education':
      return { title: text('title'), detail: [text('place'), text('dates')].filter(Boolean).join(' · ') }
    case 'experience': {
      const bullets = (value.bullets as string[]).length
      return { title: text('title'), detail: [text('place'), text('dates'), `${bullets} puce${bullets > 1 ? 's' : ''}`].filter(Boolean).join(' · ') }
    }
    case 'projects':
      return { title: text('title'), detail: [text('tag'), text('date')].filter(Boolean).join(' · ') || text('description') }
    case 'skills':
      return { title: text('label'), detail: text('text') }
    case 'languages':
      return { title: text('name'), detail: text('level') }
    default:
      return { title: text('text'), detail: '' }
  }
}

const input =
  'h-9 rounded-md border bg-background px-3 text-[13px] shadow-xs outline-none focus:border-ring focus:ring-[3px] focus:ring-ring/40'
const area =
  'resize-y rounded-md border bg-background px-3 py-2 text-[13px] leading-relaxed shadow-xs outline-none focus:border-ring focus:ring-[3px] focus:ring-ring/40'

/** Les champs d'un élément ; une rubrique de simples lignes (intérêts) n'a qu'un champ. */
export function ItemEditor({ kind, item, onChange, label }: { kind: Kind; item: Item; onChange: (item: Item) => void; label: string }) {
  if (typeof item === 'string') {
    return <input value={item} onChange={(e) => onChange(e.target.value)} aria-label={label} className={input} />
  }
  const value = item as unknown as Record<string, unknown>
  const set = (key: string, next: unknown) => onChange({ ...value, [key]: next } as unknown as Item)
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {FIELDS[kind].map((field) => {
        const name = `${field.label} (${label})`
        const raw = value[field.key]
        return (
          <label key={field.key} className={`flex flex-col gap-1.5 text-[12px] font-medium ${field.wide ? 'sm:col-span-2' : ''}`}>
            {field.label}
            {field.lines ? (
              <textarea
                value={(raw as string[]).join('\n')}
                onChange={(e) => set(field.key, e.target.value.split('\n'))}
                onBlur={(e) => set(field.key, e.target.value.split('\n').map((line) => line.trim()).filter(Boolean))}
                rows={Math.max(3, (raw as string[]).length + 1)}
                aria-label={name}
                className={area}
              />
            ) : field.multiline ? (
              <textarea value={(raw as string) ?? ''} onChange={(e) => set(field.key, e.target.value)} rows={2} aria-label={name} className={area} />
            ) : (
              <input
                value={(raw as string | null) ?? ''}
                onChange={(e) => set(field.key, field.key === 'link' ? e.target.value || null : e.target.value)}
                placeholder={field.placeholder}
                aria-label={name}
                className={input}
              />
            )}
          </label>
        )
      })}
    </div>
  )
}

/** Une rubrique s'affiche si elle a au moins un élément rempli. */
export function finalized(content: CVContent): CVContent {
  const filled = (item: Item) => (typeof item === 'string' ? item.trim() !== '' : Object.values(item as unknown as Record<string, unknown>).some((v) => (Array.isArray(v) ? v.length > 0 : typeof v === 'string' && v.trim() !== '')))
  return {
    ...content,
    sections: content.sections.map((section) => {
      const items = (section.items as Item[]).filter(filled)
      return { ...section, items, visible: items.length > 0 } as Section
    }),
  }
}

interface DoneDialogProps {
  result: ApplyBaseResult | null
  // Ce qui a été fabriqué : un CV classique de plus, ou un CV classique remplacé.
  intent: WelcomeIntent | null
  onTarget: (slug: string) => void
  onStyle: (slug: string) => void
}

export function DoneDialog({ result, intent, onTarget, onStyle }: DoneDialogProps) {
  const added = result?.added
  const slug = result?.slug ?? 'base'
  const what =
    intent?.mode === 'new'
      ? `« ${intent.name} » s'ajoute à tes CV classiques. Les autres ne bougent pas.`
      : intent?.mode === 'replace'
        ? `Il remplace « ${intent.name} », gardé dans la corbeille.`
        : 'Il remplace la version classique précédente, gardée dans la corbeille.'
  return (
    <Dialog open={result !== null}>
      <DialogContent className="sm:max-w-md" showCloseButton={false} onEscapeKeyDown={(e) => e.preventDefault()} onInteractOutside={(e) => e.preventDefault()}>
        <DialogHeader>
          <span className="mb-1 flex size-11 items-center justify-center rounded-xl bg-status-offer-soft text-status-offer">
            <CheckCircle2 className="size-6" />
          </span>
          <DialogTitle className="text-[20px]">Ton CV classique est prêt</DialogTitle>
          <DialogDescription className="text-[13.5px] leading-relaxed">
            {what}
            {added && ` Ta bibliothèque a reçu ${added.skills} compétences, ${added.experiences} expériences et ${added.projects} projets.`}
            {result && !result.compile.ok && ' La compilation a échoué : ouvre le CV pour voir l’erreur.'}
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-wrap gap-2 pt-1">
          <Button onClick={() => onTarget(slug)}>Cibler une offre avec ce CV</Button>
          <Button variant="outline" onClick={() => onStyle(slug)}>
            Ajuster le style
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
