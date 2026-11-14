import { AlertTriangle, ChevronDown, Loader2, Trash2 } from 'lucide-react'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import workerSrc from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { Document, Page, pdfjs } from 'react-pdf'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import type { Route } from '@/hooks/use-route'
import { api } from '@/lib/api'
import { clearIntent, readIntent } from '@/lib/welcome-intent'
import type { ApplyBaseResult, CVContent, ImportCheck, ImportResult, Section, StyleFinding } from '@/lib/types'
import { cn } from '@/lib/utils'

import { DoneDialog, finalized, ItemEditor, summary } from './fields'
import { FlowHeader } from './welcome-flow'

pdfjs.GlobalWorkerOptions.workerSrc = workerSrc

interface ReviewStepProps {
  id: string
  navigate: (route: Route) => void
  onTarget: (slug: string) => void
  onStyle: (slug: string) => void
  refresh: () => Promise<void>
}

// « Expérience 2, puce 1 » → la section et l'élément à ouvrir.
const WHERE: Record<string, string> = {
  Formation: 'formation',
  Expérience: 'experience',
  Engagement: 'associatif',
  Projet: 'projets',
  'Compétences :': 'competences',
  'Soft skills': 'soft-skills',
  Langues: 'langues',
  "Centres d'intérêt": 'centres-interet',
}

function target(check: ImportCheck): { section: string; item: number } | null {
  for (const [prefix, section] of Object.entries(WHERE)) {
    if (!check.where.startsWith(prefix)) continue
    const number = /^\D+?(\d+)/.exec(check.where)
    return { section, item: number ? Number(number[1]) - 1 : 0 }
  }
  return null
}

// Les compétences sont comptées par le serveur (il sait découper « scikit-learn, LightGBM »
// entre parenthèses) ; expériences et projets suivent les retouches.
function counts(content: CVContent, skills: number) {
  let experiences = 0
  let projects = 0
  for (const section of content.sections) {
    if (section.kind === 'experience') experiences += section.items.length
    if (section.kind === 'projects') projects += section.items.length
  }
  return { skills, experiences, projects }
}

/** Étape 2 : le PDF d'origine à gauche, ce que l'appli a repéré à droite, puis la validation. */
export function ReviewStep({ id, navigate, onTarget, onStyle, refresh }: ReviewStepProps) {
  // Ajout d'un CV classique, ou remplacement : lu une fois, gardé pour le message de fin.
  const [intent] = useState(readIntent)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [failed, setFailed] = useState<string | null>(null)
  const [content, setContent] = useState<CVContent | null>(null)
  const [keepPhoto, setKeepPhoto] = useState(true)
  const [open, setOpen] = useState<{ section: string; item: number | null } | null>(null)
  const [view, setView] = useState<'sections' | 'form'>('sections')
  // La forme du CV : proche de son PDF (par défaut), ou le style de l'appli.
  const [shape, setShape] = useState<'mine' | 'app'>('mine')
  // Le style repéré dans le PDF : gardé par défaut, élément par élément.
  const [findings, setFindings] = useState<StyleFinding[] | null>(null)
  const [keep, setKeep] = useState<ReadonlySet<string>>(() => new Set())
  const [applying, setApplying] = useState(false)
  const [done, setDone] = useState<ApplyBaseResult | null>(null)

  useEffect(() => {
    api.getImport(id).then(
      (loaded) => {
        setResult(loaded)
        setContent(loaded.content)
        api.importStyle(id).then(
          ({ findings: found }) => {
            setFindings(found)
            setKeep(new Set(found.filter((f) => KEEPABLE.has(f.key)).map((f) => f.key)))
          },
          () => setFindings([]),
        )
      },
      (error: Error) => setFailed(error.message),
    )
  }, [id])

  const back = () => navigate({ view: 'welcome', step: 'import' })
  if (failed) {
    return (
      <>
        <FlowHeader back={back} current={1} />
        <p role="alert" className="mx-auto max-w-lg px-6 py-16 text-center text-[14px] text-muted-foreground">{failed}</p>
      </>
    )
  }
  if (!result || !content) {
    return (
      <>
        <FlowHeader back={back} current={1} />
        <div className="flex justify-center py-24"><Loader2 className="size-6 animate-spin text-muted-foreground" /></div>
      </>
    )
  }

  const final = () => {
    const cleaned = finalized(content)
    return { ...cleaned, header: { ...cleaned.header, photo: result.photo && keepPhoto ? cleaned.header.photo : '' } }
  }
  const setHeader = (key: 'name' | 'headline' | 'summary', value: string) => setContent({ ...content, header: { ...content.header, [key]: value } })
  const setSection = (index: number, section: Section) => setContent({ ...content, sections: content.sections.map((s, i) => (i === index ? section : s)) })
  const validate = async () => {
    setApplying(true)
    try {
      const applied = await api.applyBase(final(), id, keepPhoto, shape === 'mine' ? styleKeep : null, intent)
      clearIntent()
      await refresh()
      setDone(applied)
    } catch (error) {
      toast.error('Validation impossible', { description: error instanceof Error ? error.message : String(error) })
    } finally {
      setApplying(false)
    }
  }
  const total = counts(content, result.counts.skills)
  const mine = shape === 'mine'
  const styleKeep = mine && findings?.length ? [...keep].sort() : null

  return (
    <>
      <FlowHeader back={back} current={1} />
      <main className="mx-auto flex w-full max-w-[1320px] flex-wrap gap-7 px-6 pt-7 pb-32">
        <section aria-label="Ton PDF d'origine" className="flex min-w-0 flex-[1_1_400px] flex-col gap-2.5">
          <div className="flex items-baseline justify-between">
            <h2 className="text-[13px] font-semibold text-foreground/80">Ton PDF d'origine</h2>
          </div>
          <PdfView url={api.importSourceUrl(id)} />
        </section>

        <section aria-label="Ce que l'appli a repéré" className="flex min-w-0 flex-[999_1_560px] flex-col gap-4">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="flex-1 text-[23px] font-semibold tracking-tight">Relis ce que l'appli a repéré</h1>
            <div role="radiogroup" aria-label="Affichage" className="flex gap-0.5 rounded-lg bg-muted p-0.5">
              {(
                [
                  ['sections', 'Rubriques'],
                  ['form', 'Forme'],
                ] as const
              ).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  role="radio"
                  aria-checked={view === key}
                  onClick={() => setView(key)}
                  className={cn('h-7 rounded-md px-3 text-[12.5px] font-medium', view === key ? 'bg-background shadow-xs' : 'text-muted-foreground hover:text-foreground')}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {result.checks.length > 0 && (
            <div role="note" aria-label="Points à vérifier" className="flex flex-col gap-2.5 rounded-xl border border-status-interview/30 bg-status-interview-soft/70 p-4">
              <span className="flex items-center gap-2 text-[13.5px] font-semibold text-status-interview">
                <AlertTriangle className="size-4" /> {result.checks.length} point{result.checks.length > 1 ? 's' : ''} à vérifier
              </span>
              {result.checks.map((check, i) => {
                const place = target(check)
                return (
                  <div key={i} className="flex flex-wrap items-center gap-2.5 text-[13px]">
                    <span className="min-w-60 flex-1">
                      <span className="font-medium">{check.where} : </span>
                      {check.text}
                    </span>
                    {place && (
                      <Button size="sm" variant="outline" className="h-7 bg-background text-[12px]" onClick={() => { setView('sections'); setOpen(place) }}>
                        Voir
                      </Button>
                    )}
                  </div>
                )
              })}
            </div>
          )}

          {view === 'form' ? (
            <div className="flex flex-col gap-4">
              <div role="radiogroup" aria-label="Forme du CV" className="grid grid-cols-1 gap-2.5 md:grid-cols-2">
                {(
                  [
                    ['mine', 'Proche du mien', 'Notre mise en page, avec ta police, tes couleurs, tes colonnes et ton en-tête.'],
                    ['app', "Style de l'appli", "Le style par défaut, que tu changeras dans l'onglet Style."],
                  ] as const
                ).map(([value, title, hint]) => (
                  <button
                    key={value}
                    type="button"
                    role="radio"
                    aria-checked={shape === value}
                    onClick={() => setShape(value)}
                    className={cn(
                      'flex flex-col items-start gap-1.5 rounded-xl border bg-card surface px-4 py-3.5 text-left transition-colors',
                      shape === value ? 'border-primary ring-2 ring-primary/15' : 'hover:border-primary/40',
                    )}
                  >
                    <span className="flex items-center gap-2 text-[14px] font-semibold">
                      <span className={cn('size-4 shrink-0 rounded-full border-[1.5px]', shape === value ? 'border-[5px] border-primary' : 'border-muted-foreground/50')} />
                      {title}
                    </span>
                    <span className="pl-6 text-[12.5px] text-muted-foreground">{hint}</span>
                  </button>
                ))}
              </div>
            <StylePanel
              id={id}
              content={final()}
              findings={findings}
              mine={mine}
              setMine={(value) => setShape(value ? 'mine' : 'app')}
              keep={keep}
              toggle={(key) =>
                setKeep((current) => {
                  const next = new Set(current)
                  if (next.has(key)) next.delete(key)
                  else next.add(key)
                  return next
                })
              }
              styleKeep={styleKeep}
              showChoices={false}
            />
            </div>
          ) : (
            <div className="flex flex-col overflow-hidden rounded-xl border bg-card surface">
              <div className="flex flex-col gap-3.5 p-4.5">
                <div className="flex items-center gap-2">
                  <h2 className="flex-1 text-[15px] font-semibold">Identité</h2>
                  {result.photo && <span className="text-[12px] font-semibold text-status-offer">Photo trouvée dans le PDF</span>}
                </div>
                <div className="flex flex-wrap gap-4">
                  {result.photo && (
                    <div className="flex flex-col items-center gap-2">
                      <img src={api.importPhotoUrl(id)} alt="Photo trouvée dans le PDF" className={cn('size-18 rounded-lg border object-cover', !keepPhoto && 'opacity-40 grayscale')} />
                      <label className="flex items-center gap-1.5 text-[12px]">
                        <input type="checkbox" checked={keepPhoto} onChange={(e) => setKeepPhoto(e.target.checked)} /> Garder
                      </label>
                    </div>
                  )}
                  <div className="grid min-w-72 flex-1 grid-cols-1 gap-3 sm:grid-cols-2">
                    <Field label="Nom" value={content.header.name} onChange={(v) => setHeader('name', v)} />
                    <Field label="Titre" value={content.header.headline} onChange={(v) => setHeader('headline', v)} />
                    <label className="flex flex-col gap-1.5 text-[12px] font-medium sm:col-span-2">
                      Accroche
                      <textarea value={content.header.summary} onChange={(e) => setHeader('summary', e.target.value)} rows={2} className="resize-y rounded-md border bg-background px-3 py-2 text-[13px] shadow-xs outline-none focus:border-ring focus:ring-[3px] focus:ring-ring/40" />
                    </label>
                    <div className="flex flex-wrap gap-1.5 sm:col-span-2" aria-label="Coordonnées">
                      {content.header.contact_lines.flat().map((contact, i) => (
                        <span key={i} className="rounded-full bg-muted px-2.5 py-1 text-[12px]">
                          {contact.label ? `${contact.label} : ` : ''}
                          {contact.text}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
              {content.sections.map((section, index) => {
                if (section.items.length === 0) return null
                const expanded = open?.section === section.id
                return (
                  <div key={section.id} className="border-t">
                    <button
                      type="button"
                      aria-expanded={expanded}
                      onClick={() => setOpen(expanded ? null : { section: section.id, item: null })}
                      className="flex w-full items-center gap-3 px-4.5 py-3.5 text-left hover:bg-muted/50"
                    >
                      <span className="flex-1 text-[14.5px] font-semibold">{section.title}</span>
                      <span className="text-[12.5px] text-muted-foreground">{section.items.length}</span>
                      <ChevronDown className={cn('size-4 text-muted-foreground transition-transform', expanded && 'rotate-180')} />
                    </button>
                    {expanded && (
                      <div className="flex flex-col gap-2 px-4.5 pb-4">
                        {(section.items as Section['items'][number][]).map((item, i) => {
                          const { title, detail } = summary(section.kind, item)
                          const editing = open?.item === i
                          const label = `${section.title.toLowerCase()} ${i + 1}`
                          return (
                            <div key={i} className={cn('rounded-lg border p-3', editing && 'border-primary/40 ring-1 ring-primary/15')}>
                              <div className="flex items-start gap-3">
                                <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                                  <span className="text-[13.5px] font-semibold">{title || '(sans titre)'}</span>
                                  {detail && <span className="text-[12.5px] text-muted-foreground">{detail}</span>}
                                </div>
                                <Button size="sm" variant="outline" className="h-7 text-[12px]" onClick={() => setOpen({ section: section.id, item: editing ? null : i })}>
                                  {editing ? 'Fermer' : 'Modifier'}
                                </Button>
                              </div>
                              {editing && (
                                <div className="mt-3 flex flex-col gap-3 border-t pt-3">
                                  <ItemEditor
                                    kind={section.kind}
                                    item={item}
                                    label={label}
                                    onChange={(next) => setSection(index, { ...section, items: section.items.map((old, j) => (j === i ? next : old)) } as Section)}
                                  />
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    className="h-7 self-start text-[12px] text-destructive"
                                    onClick={() => {
                                      setSection(index, { ...section, items: section.items.filter((_, j) => j !== i) } as Section)
                                      setOpen({ section: section.id, item: null })
                                    }}
                                  >
                                    <Trash2 className="size-3.5" /> Retirer
                                  </Button>
                                </div>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </section>
      </main>

      <div className="fixed inset-x-0 bottom-0 flex flex-wrap items-center gap-3 border-t bg-background/95 px-6 py-3.5 backdrop-blur">
        <span className="min-w-72 flex-1 text-[13px] text-foreground/85">
          Ta bibliothèque recevra <strong>{total.skills} compétences</strong>, <strong>{total.experiences} expériences</strong> et{' '}
          <strong>{total.projects} projets</strong>, déjà validés.
        </span>
        <Button variant="ghost" onClick={back}>
          Recommencer
        </Button>
        <Button onClick={() => void validate()} disabled={applying || !content.header.name.trim()} className="h-10 px-5">
          {applying && <Loader2 className="size-4 animate-spin" />} Valider ce CV
        </Button>
      </div>
      <DoneDialog result={done} intent={intent} onTarget={onTarget} onStyle={onStyle} />
    </>
  )
}

function Field({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="flex flex-col gap-1.5 text-[12px] font-medium">
      {label}
      <input value={value} onChange={(e) => onChange(e.target.value)} className="h-9 rounded-md border bg-background px-3 text-[13px] shadow-xs outline-none focus:border-ring focus:ring-[3px] focus:ring-ring/40" />
    </label>
  )
}

/** Un PDF à la largeur de sa colonne. */
function PdfView({ url }: { url: string }) {
  const box = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(0)
  useLayoutEffect(() => {
    const element = box.current
    if (!element) return
    const observer = new ResizeObserver(([entry]) => setWidth(Math.floor(entry.contentRect.width)))
    observer.observe(element)
    return () => observer.disconnect()
  }, [])
  return (
    <div ref={box} className="overflow-hidden rounded-md border bg-white shadow-md">
      {width > 0 && (
        <Document file={url} loading={<div className="aspect-[1/1.414] animate-pulse bg-muted" />} error={<p className="p-6 text-[13px] text-muted-foreground">Ce PDF ne s'affiche pas.</p>}>
          <Page pageNumber={1} width={width} renderAnnotationLayer={false} renderTextLayer={false} />
        </Document>
      )}
    </div>
  )
}

function Preview({ id, content, keep }: { id: string; content: CVContent; keep: string[] | null }) {
  const [state, setState] = useState<{ url: string } | { error: string } | null>(null)
  const json = JSON.stringify(content)
  const kept = keep === null ? null : keep.join(',')
  useEffect(() => {
    let live = true
    setState(null)
    api.previewImport(id, JSON.parse(json) as CVContent, kept === null ? null : kept.split(',').filter(Boolean)).then(
      (compiled) => live && setState(compiled.ok ? { url: api.importPreviewUrl(id, Date.now()) } : { error: 'La mise au format a échoué : valide quand même, puis ouvre le CV pour voir l’erreur.' }),
      (error: Error) => live && setState({ error: error.message }),
    )
    return () => {
      live = false
    }
  }, [id, json, kept])
  if (state === null) {
    return (
      <div className="flex items-center justify-center gap-2 rounded-xl border bg-card surface py-24 text-[13px] text-muted-foreground">
        <Loader2 className="size-4 animate-spin" /> Mise au format de l'appli…
      </div>
    )
  }
  if ('error' in state) return <p className="rounded-xl border bg-card surface p-6 text-[13px] text-muted-foreground">{state.error}</p>
  return <PdfView url={state.url} />
}

// Ce qui s'applique au style ; le reste (les icônes) n'est qu'une information.
const KEEPABLE = new Set(['font', 'colors', 'photo', 'columns', 'titles', 'sizes', 'header', 'order', 'bullets'])

const BADGE: Record<StyleFinding['badge'], string> = {
  identique: 'bg-status-offer-soft text-status-offer',
  proche: 'bg-status-sent-soft text-status-sent',
  approché: 'bg-status-interview-soft text-status-interview',
}

interface StylePanelProps {
  id: string
  content: CVContent
  findings: StyleFinding[] | null
  // Les deux choix (proche du mien / style de l'appli) ; masqués quand l'onglet Forme les porte.
  showChoices?: boolean
  mine: boolean
  setMine: (mine: boolean) => void
  keep: ReadonlySet<string>
  toggle: (key: string) => void
  styleKeep: string[] | null
}

/** Le style repéré dans le PDF : le garder (élément par élément) ou partir de celui de l'appli. */
function StylePanel({ id, content, findings, mine, setMine, keep, toggle, styleKeep, showChoices = true }: StylePanelProps) {
  if (findings === null) {
    return (
      <div className="flex items-center justify-center gap-2 rounded-xl border bg-card surface py-24 text-[13px] text-muted-foreground">
        <Loader2 className="size-4 animate-spin" /> Lecture du style du PDF…
      </div>
    )
  }
  if (findings.length === 0) {
    // Un scan, souvent : rien à reprendre, mais l'aperçu de notre forme reste là.
    return (
      <div className="flex flex-wrap items-start gap-4">
        <p className="min-w-0 flex-[999_1_300px] rounded-xl border bg-card surface p-5 text-[13px] text-muted-foreground">
          L'appli n'a pas su lire le style de ce PDF (une image, par exemple) : notre forme prend le style de l'appli, que tu changeras dans l'onglet Style.
        </p>
        <div className="flex min-w-0 flex-[1_1_260px] flex-col gap-2 sm:max-w-[320px]">
          <span className="text-[12.5px] font-semibold text-foreground/80">Ton CV de base, au format de l'appli</span>
          <Preview id={id} content={content} keep={null} />
        </div>
      </div>
    )
  }
  const choices = [
    [true, 'Garder un style proche du mien', 'Police, couleurs, photo, colonnes et ordre des rubriques repris de ton PDF.'],
    [false, "Partir du style de l'appli", "Le style par défaut, que tu changeras quand tu veux dans l'onglet Style."],
  ] as const
  return (
    <div className="flex flex-col gap-4">
      {showChoices && <div role="radiogroup" aria-label="Style du CV de base" className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
        {choices.map(([value, title, hint]) => (
          <button
            key={title}
            type="button"
            role="radio"
            aria-checked={mine === value}
            onClick={() => setMine(value)}
            className={cn(
              'flex flex-col items-start gap-1.5 rounded-xl border bg-card surface px-4 py-3.5 text-left transition-colors',
              mine === value ? 'border-primary ring-2 ring-primary/15' : 'hover:border-primary/40',
            )}
          >
            <span className="flex items-center gap-2 text-[14px] font-semibold">
              <span className={cn('size-4 rounded-full border-[1.5px]', mine === value ? 'border-[5px] border-primary' : 'border-muted-foreground/50')} />
              {title}
            </span>
            <span className="pl-6 text-[12.5px] text-muted-foreground">{hint}</span>
          </button>
        ))}
      </div>}
      <div className="flex flex-wrap items-start gap-4">
        <div className={cn('flex min-w-0 flex-[999_1_380px] flex-col rounded-xl border bg-card surface', !mine && 'opacity-60')}>
          <div className="flex items-center gap-2 border-b px-4 py-3">
            <span className="flex-1 text-[13.5px] font-semibold">Repéré dans ton PDF</span>
            <span className="text-[12px] text-muted-foreground">Sans IA : rien n'est envoyé</span>
          </div>
          {findings.map((finding, i) => {
            const keepable = KEEPABLE.has(finding.key)
            return (
              <label key={`${finding.key}-${i}`} className={cn('flex gap-3 px-4 py-3', i > 0 && 'border-t', keepable && mine && 'cursor-pointer')}>
                {keepable ? (
                  <input
                    type="checkbox"
                    checked={mine && keep.has(finding.key)}
                    disabled={!mine}
                    onChange={() => toggle(finding.key)}
                    aria-label={`Reprendre : ${finding.label}`}
                    className="mt-0.5 size-4 shrink-0 accent-primary"
                  />
                ) : (
                  <span className="size-4 shrink-0" />
                )}
                <span className="flex min-w-0 flex-col gap-0.5">
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="text-[13px] font-semibold">{finding.label}</span>
                    <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-semibold', BADGE[finding.badge])}>{finding.badge}</span>
                  </span>
                  <span className="text-[12.5px] text-foreground/80">{finding.found}</span>
                  <span className="text-[12.5px] text-muted-foreground">→ {finding.done}</span>
                </span>
              </label>
            )
          })}
        </div>
        <div className="flex min-w-0 flex-[1_1_260px] flex-col gap-2 sm:max-w-[320px]">
          <span className="text-[12.5px] font-semibold text-foreground/80">Ton CV de base, au format de l'appli</span>
          <Preview id={id} content={content} keep={styleKeep} />
        </div>
      </div>
    </div>
  )
}

