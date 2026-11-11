import { Check, Loader2, Plus, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import type { Route } from '@/hooks/use-route'
import { api } from '@/lib/api'
import { clearIntent, readIntent } from '@/lib/welcome-intent'
import type { ApplyBaseResult, ContactItem, CVContent, Section } from '@/lib/types'
import { cn } from '@/lib/utils'

import { blankItem, DoneDialog, finalized, ItemEditor } from './fields'
import { FlowHeader } from './welcome-flow'

const DRAFT = 'cv-builder.welcome.manual'

interface Contacts {
  city: string
  phone: string
  email: string
  linkedin: string
  github: string
  other: string
}

interface Draft {
  content: CVContent
  contacts: Contacts
  step: number
}

const STEPS: { label: string; sections: string[]; title: string; intro: string }[] = [
  { label: 'Coordonnées', sections: [], title: 'Qui tu es', intro: "Ton nom, le titre sous ton nom, une accroche de deux lignes, et comment te joindre." },
  { label: 'Formation', sections: ['formation'], title: 'Ta formation', intro: 'Diplômes en cours et obtenus, du plus récent au plus ancien.' },
  {
    label: 'Expériences',
    sections: ['experience', 'associatif'],
    title: 'Tes expériences',
    intro: "Stages, jobs, alternance. Écris toutes les puces vraies, même s'il y en a trop pour une page : pour chaque offre, l'IA choisira les plus utiles.",
  },
  { label: 'Projets', sections: ['projets'], title: 'Tes projets', intro: "Projets d'école, personnels ou en équipe, avec leur lien s'il existe." },
  { label: 'Compétences', sections: ['competences', 'soft-skills'], title: 'Tes compétences', intro: 'Par groupes : langages, outils, méthodes… Et tes qualités, une par ligne.' },
  { label: 'Langues et intérêts', sections: ['langues', 'centres-interet'], title: 'Langues et centres d’intérêt', intro: 'Tes langues avec leur niveau, puis ce qui t’occupe en dehors.' },
]

const ADD: Record<string, string> = {
  formation: 'Ajouter une formation',
  experience: 'Ajouter une expérience',
  associatif: 'Ajouter un engagement',
  projets: 'Ajouter un projet',
  competences: 'Ajouter un groupe',
  langues: 'Ajouter une langue',
}

const EMPTY_CONTACTS: Contacts = { city: '', phone: '', email: '', linkedin: '', github: '', other: '' }

function loadDraft(): Draft | null {
  try {
    const raw = localStorage.getItem(DRAFT)
    return raw ? (JSON.parse(raw) as Draft) : null
  } catch {
    return null
  }
}

function link(text: string): string {
  return /^https?:\/\//.test(text) ? text : `https://${text}`
}

/** Les coordonnées saisies, en deux lignes comme sur le CV. */
function contactLines(c: Contacts): ContactItem[][] {
  const first: ContactItem[] = []
  const second: ContactItem[] = []
  if (c.city.trim()) first.push({ text: c.city.trim(), bold: true })
  if (c.phone.trim()) first.push({ text: c.phone.trim(), label: 'Téléphone', bold: false })
  if (c.email.trim()) first.push({ text: c.email.trim(), label: 'Email', url: `mailto:${c.email.trim()}`, bold: false })
  if (c.linkedin.trim()) second.push({ text: c.linkedin.trim().replace(/^https?:\/\/(www\.)?/, ''), label: 'LinkedIn', url: link(c.linkedin.trim()), bold: false })
  if (c.github.trim()) second.push({ text: c.github.trim().replace(/^https?:\/\//, ''), label: 'GitHub', url: link(c.github.trim()), bold: false })
  if (c.other.trim()) second.push({ text: c.other.trim(), bold: true })
  return [first, second].filter((line) => line.length > 0)
}

/** La saisie à la main, section par section ; le brouillon reste dans le navigateur. */
export function ManualStep({ navigate, onTarget, onStyle, refresh }: { navigate: (route: Route) => void; onTarget: (slug: string) => void; onStyle: (slug: string) => void; refresh: () => Promise<void> }) {
  const [intent] = useState(readIntent)
  const [draft, setDraft] = useState<Draft | null>(loadDraft)
  const [saving, setSaving] = useState(false)
  const [done, setDone] = useState<ApplyBaseResult | null>(null)

  useEffect(() => {
    if (draft) return
    api.blankCV().then(
      (content) => setDraft({ content, contacts: EMPTY_CONTACTS, step: 0 }),
      (error: Error) => toast.error('Saisie indisponible', { description: error.message }),
    )
  }, [draft])
  useEffect(() => {
    if (!draft) return
    try {
      localStorage.setItem(DRAFT, JSON.stringify(draft))
    } catch {
      /* brouillon gardé pour cette visite seulement */
    }
  }, [draft])

  const back = () => navigate({ view: 'welcome', step: 'home' })
  if (!draft) {
    return (
      <>
        <FlowHeader back={back} title="Ton CV de base, à la main" />
        <div className="flex justify-center py-24"><Loader2 className="size-6 animate-spin text-muted-foreground" /></div>
      </>
    )
  }

  const { content, contacts, step } = draft
  const go = (next: number) => setDraft({ ...draft, step: Math.max(0, Math.min(STEPS.length - 1, next)) })
  const setHeader = (key: 'name' | 'headline' | 'summary', value: string) => setDraft({ ...draft, content: { ...content, header: { ...content.header, [key]: value } } })
  const setContacts = (key: keyof Contacts, value: string) => setDraft({ ...draft, contacts: { ...contacts, [key]: value } })
  const setSection = (id: string, update: (section: Section) => Section) =>
    setDraft({ ...draft, content: { ...content, sections: content.sections.map((s) => (s.id === id ? update(s) : s)) } })
  const sectionCount = (ids: string[]) => content.sections.filter((s) => ids.includes(s.id)).reduce((n, s) => n + s.items.length, 0)

  const finish = async () => {
    if (!content.header.name.trim()) {
      go(0)
      toast.error('Il manque ton nom', { description: 'Il ouvre le CV : remplis-le dans « Coordonnées ».' })
      return
    }
    setSaving(true)
    try {
      const final = finalized({ ...content, header: { ...content.header, contact_lines: contactLines(contacts), photo: '' } })
      const applied = await api.applyBase(final, undefined, true, null, intent)
      clearIntent()
      try {
        localStorage.removeItem(DRAFT)
      } catch {
        /* rien à effacer */
      }
      await refresh()
      setDone(applied)
    } catch (error) {
      toast.error('Enregistrement impossible', { description: error instanceof Error ? error.message : String(error) })
    } finally {
      setSaving(false)
    }
  }

  const current = STEPS[step]
  const last = step === STEPS.length - 1
  return (
    <>
      <FlowHeader back={back} title="Ton CV de base, à la main" aside="Brouillon gardé" />
      <main className="mx-auto flex w-full max-w-[1180px] flex-wrap gap-8 px-6 py-8">
        <nav aria-label="Sections" className="flex flex-[0_1_240px] flex-col gap-1">
          {STEPS.map((s, i) => {
            const filled = i === 0 ? content.header.name.trim() !== '' : sectionCount(s.sections) > 0
            return (
              <button
                key={s.label}
                type="button"
                onClick={() => go(i)}
                aria-current={i === step ? 'step' : undefined}
                className={cn('flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13.5px] transition-colors', i === step ? 'bg-accent font-semibold' : 'hover:bg-muted')}
              >
                <span
                  className={cn(
                    'flex size-5.5 shrink-0 items-center justify-center rounded-full text-[11.5px] font-semibold',
                    i === step ? 'bg-primary text-primary-foreground' : filled ? 'bg-status-offer-soft text-status-offer' : 'border text-muted-foreground',
                  )}
                >
                  {filled && i !== step ? <Check className="size-3" /> : i + 1}
                </span>
                <span className="flex-1">{s.label}</span>
                {i > 0 && sectionCount(s.sections) > 0 && <span className="text-[12px] font-normal text-muted-foreground">{sectionCount(s.sections)}</span>}
              </button>
            )
          })}
          <p className="mt-3 rounded-lg bg-muted/70 p-3 text-[12.5px] leading-relaxed text-foreground/80">
            Tu peux t'arrêter à tout moment : la saisie reprend là où tu l'as laissée. La photo s'ajoute ensuite, dans l'onglet Style.
          </p>
        </nav>

        <section className="flex min-w-0 flex-[999_1_560px] flex-col gap-5">
          <div className="flex flex-col gap-1.5">
            <span className="text-[12.5px] font-semibold text-primary">
              Étape {step + 1} sur {STEPS.length}
            </span>
            <h1 className="text-[25px] font-semibold tracking-tight">{current.title}</h1>
            <p className="max-w-prose text-[14px] leading-relaxed text-muted-foreground">{current.intro}</p>
          </div>

          {step === 0 && (
            <div className="grid grid-cols-1 gap-3.5 rounded-xl border bg-card surface p-5 sm:grid-cols-2">
              <Input label="Nom et prénom" value={content.header.name} onChange={(v) => setHeader('name', v)} placeholder="ex. Camille Laurent" />
              <Input label="Titre sous le nom" value={content.header.headline} onChange={(v) => setHeader('headline', v)} placeholder="ex. Élève ingénieur | Data & IA" />
              <label className="flex flex-col gap-1.5 text-[12px] font-medium sm:col-span-2">
                Accroche
                <textarea value={content.header.summary} onChange={(e) => setHeader('summary', e.target.value)} rows={2} placeholder="Ce que tu cherches et ce que tu apportes, en deux lignes." className="resize-y rounded-md border bg-background px-3 py-2 text-[13px] shadow-xs outline-none focus:border-ring focus:ring-[3px] focus:ring-ring/40" />
              </label>
              <Input label="Ville" value={contacts.city} onChange={(v) => setContacts('city', v)} placeholder="ex. Lyon, France" />
              <Input label="Téléphone" value={contacts.phone} onChange={(v) => setContacts('phone', v)} />
              <Input label="Email" value={contacts.email} onChange={(v) => setContacts('email', v)} />
              <Input label="LinkedIn" value={contacts.linkedin} onChange={(v) => setContacts('linkedin', v)} placeholder="linkedin.com/in/…" />
              <Input label="GitHub" value={contacts.github} onChange={(v) => setContacts('github', v)} placeholder="github.com/…" />
              <Input label="Autre mention, facultative" value={contacts.other} onChange={(v) => setContacts('other', v)} placeholder="ex. Permis B" />
            </div>
          )}

          {current.sections.map((id) => {
            const section = content.sections.find((s) => s.id === id)
            if (!section) return null
            const optional = id === 'associatif'
            if (section.kind === 'grid' || section.kind === 'bullets') {
              const lines = section.kind === 'grid' ? section.items.map((item) => item.text) : section.items
              return (
                <label key={id} className="flex flex-col gap-1.5 rounded-xl border bg-card surface p-5 text-[13px] font-semibold">
                  {section.kind === 'grid' ? 'Tes qualités, une par ligne' : 'Tes centres d’intérêt, un par ligne'}
                  <textarea
                    value={lines.join('\n')}
                    rows={Math.max(4, lines.length + 1)}
                    onChange={(e) => {
                      const next = e.target.value.split('\n')
                      setSection(id, (s) =>
                        (s.kind === 'grid' ? { ...s, items: next.map((text) => ({ text, wide: text.length > 22 })) } : { ...s, items: next }) as Section,
                      )
                    }}
                    className="resize-y rounded-md border bg-background px-3 py-2 text-[13px] font-normal shadow-xs outline-none focus:border-ring focus:ring-[3px] focus:ring-ring/40"
                  />
                </label>
              )
            }
            return (
              <div key={id} className="flex flex-col gap-3">
                {optional && <h2 className="pt-2 text-[15px] font-semibold">Engagement associatif, facultatif</h2>}
                {(section.items as Section['items'][number][]).map((item, i) => (
                  <article key={i} className="flex flex-col gap-3 rounded-xl border bg-card surface p-5">
                    <ItemEditor
                      kind={section.kind}
                      item={item}
                      label={`${section.title.toLowerCase()} ${i + 1}`}
                      onChange={(next) => setSection(id, (s) => ({ ...s, items: s.items.map((old, j) => (j === i ? next : old)) }) as Section)}
                    />
                    <Button size="sm" variant="ghost" className="h-7 self-start text-[12px] text-destructive" onClick={() => setSection(id, (s) => ({ ...s, items: s.items.filter((_, j) => j !== i) }) as Section)}>
                      <Trash2 className="size-3.5" /> Retirer
                    </Button>
                  </article>
                ))}
                <button
                  type="button"
                  onClick={() => setSection(id, (s) => ({ ...s, items: [...s.items, blankItem(s.kind)] }) as Section)}
                  className="flex h-12 items-center justify-center gap-2 rounded-xl border-[1.5px] border-dashed border-primary/30 text-[13.5px] font-semibold text-primary transition-colors hover:bg-primary/5"
                >
                  <Plus className="size-4" /> {ADD[id] ?? 'Ajouter'}
                </button>
              </div>
            )
          })}

          <div className="flex flex-wrap items-center gap-2.5 pt-1">
            <Button variant="outline" onClick={() => go(step - 1)} disabled={step === 0}>
              Précédent
            </Button>
            <span className="flex-1" />
            {!last && (
              <Button variant="ghost" onClick={() => go(step + 1)}>
                Passer cette étape
              </Button>
            )}
            {last ? (
              <Button onClick={() => void finish()} disabled={saving}>
                {saving && <Loader2 className="size-4 animate-spin" />} Terminer mon CV
              </Button>
            ) : (
              <Button onClick={() => go(step + 1)}>Suivant : {STEPS[step + 1].label.toLowerCase()}</Button>
            )}
          </div>
        </section>
      </main>
      <DoneDialog result={done} intent={intent} onTarget={onTarget} onStyle={onStyle} />
    </>
  )
}

function Input({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (value: string) => void; placeholder?: string }) {
  return (
    <label className="flex flex-col gap-1.5 text-[12px] font-medium">
      {label}
      <input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} className="h-9 rounded-md border bg-background px-3 text-[13px] shadow-xs outline-none focus:border-ring focus:ring-[3px] focus:ring-ring/40" />
    </label>
  )
}
