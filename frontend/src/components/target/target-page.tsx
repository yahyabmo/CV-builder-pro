import { CircleAlert, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import { ScrollArea } from '@/components/ui/scroll-area'
import type { Route } from '@/hooks/use-route'
import { api } from '@/lib/api'
import { lastBase } from '@/lib/bases'
import type { ApplyResult, CVSummary, Draft, TargetEvent, TargetRequest } from '@/lib/types'
import { cn } from '@/lib/utils'

import { OfferForm, type OfferDraft } from './offer-form'
import { ProgressPanel, type RunState } from './progress-panel'
import { ResultPanel } from './result-panel'
import { acceptedTexts, carryDecisions, confirmedTerms, initialDecisions, type Decisions } from './decisions'
import { Review } from './review'

// Une proposition en cours de relecture survit à un changement de page.
const STORE = 'cv-builder.target'

type Phase =
  | { step: 'form' }
  | { step: 'running'; run: RunState }
  | { step: 'review'; draft: Draft }
  | { step: 'done'; draft: Draft; result: ApplyResult }

interface Stored {
  draft: string
  decisions: Decisions
  name: string
}

function readStore(): Stored | null {
  try {
    const raw = localStorage.getItem(STORE)
    return raw ? (JSON.parse(raw) as Stored) : null
  } catch {
    return null
  }
}

function writeStore(value: Stored | null) {
  try {
    if (value) localStorage.setItem(STORE, JSON.stringify(value))
    else localStorage.removeItem(STORE)
  } catch {
    /* la relecture vaut pour cette page */
  }
}

function defaultName(draft: Draft): string {
  const { company, job_title } = draft.analysis
  return [company, job_title].filter(Boolean).join(' – ').slice(0, 120) || 'CV ciblé'
}

const STEPS = [
  ['form', "L'offre"],
  ['review', 'Propositions'],
  ['done', 'CV créé'],
] as const

interface TargetPageProps {
  cvs: CVSummary[] | null
  source?: string
  navigate: (route: Route) => void
  refresh: () => Promise<void>
}

export function TargetPage({ cvs, source, navigate, refresh }: TargetPageProps) {
  const [phase, setPhase] = useState<Phase>({ step: 'form' })
  const [form, setForm] = useState<OfferDraft>({
    source: source ?? lastBase(cvs),
    mode: 'text',
    text: '',
    url: '',
    projects: 'auto',
    language: 'auto',
  })
  const [error, setError] = useState<string | null>(null)
  const [decisions, setDecisions] = useState<Decisions | null>(null)
  const [name, setName] = useState('')
  const [applying, setApplying] = useState(false)
  const [cutting, setCutting] = useState<string | null>(null)
  const abort = useRef<AbortController | null>(null)

  // Reprise d'une relecture laissée en cours.
  useEffect(() => {
    const stored = readStore()
    if (!stored) return
    api.getDraft(stored.draft).then(
      (draft) => {
        setDecisions(stored.decisions)
        setName(stored.name)
        setPhase((current) => (current.step === 'form' ? { step: 'review', draft } : current))
      },
      () => writeStore(null),
    )
  }, [])

  useEffect(() => {
    if (phase.step === 'review' && decisions) writeStore({ draft: phase.draft.id, decisions, name })
  }, [phase, decisions, name])

  useEffect(() => () => abort.current?.abort(), [])

  /** Suit un flux de progression jusqu'à la proposition, l'erreur ou l'annulation. */
  const follow = useCallback(
    async (call: (onEvent: (event: TargetEvent) => void, signal: AbortSignal) => Promise<void>, expected: string[]) => {
      const controller = new AbortController()
      abort.current = controller
      setPhase({ step: 'running', run: { steps: [], wait: null, started: Date.now(), expected } })
      let found: Draft | null = null
      let failure: string | null = null
      const step = (update: (run: RunState) => RunState) =>
        setPhase((current) => (current.step === 'running' ? { step: 'running', run: update(current.run) } : current))
      try {
        await call((event) => {
          if (event.type === 'step') step((run) => ({ ...run, steps: [...run.steps, event.label], wait: null }))
          else if (event.type === 'wait') step((run) => ({ ...run, wait: event.message }))
          else if (event.type === 'done') found = event.draft
          else failure = event.message
        }, controller.signal)
      } catch (caught) {
        if (!controller.signal.aborted) failure = (caught as Error).message
      }
      return {
        draft: found as Draft | null,
        failure: failure ?? 'Le serveur a coupé la connexion avant la fin.',
        aborted: controller.signal.aborted,
      }
    },
    [],
  )

  const start = async (request: TargetRequest) => {
    setError(null)
    const { draft, failure, aborted } = await follow(
      (onEvent, signal) => api.target(request, onEvent, signal),
      [...(request.url ? ['Lecture de la page'] : []), "Analyse de l'offre", 'Compétences et projets', 'Formulations'],
    )
    if (draft) {
      setDecisions(initialDecisions(draft))
      setName(defaultName(draft))
      setPhase({ step: 'review', draft })
      return
    }
    if (!aborted) setError(failure)
    setPhase({ step: 'form' })
  }

  const rerun = async (old: Draft) => {
    if (!decisions) return
    const previous = decisions
    const translating = old.language !== old.source_language
    const { draft, failure, aborted } = await follow(
      (onEvent, signal) => api.rerun(old.id, onEvent, signal),
      ['Compétences et projets', 'Formulations', ...(translating ? [`Traduction en ${old.language === 'en' ? 'anglais' : 'français'}`] : [])],
    )
    if (draft) {
      setDecisions(carryDecisions(old, previous, draft))
      setPhase({ step: 'review', draft })
      return
    }
    setPhase({ step: 'review', draft: old })
    if (!aborted) toast.error('Relance impossible', { description: failure })
  }

  const discard = () => {
    writeStore(null)
    setDecisions(null)
    setPhase({ step: 'form' })
  }

  const apply = async (draft: Draft) => {
    if (!decisions) return
    setApplying(true)
    try {
      const edits = decisions.accepted.translation ? decisions.translation : {}
      const result = await api.applyDraft(draft.id, name.trim(), acceptedTexts(draft, decisions), edits, confirmedTerms(draft, decisions))
      writeStore(null)
      setPhase({ step: 'done', draft, result })
      void refresh()
    } catch (caught) {
      toast.error('Création du CV impossible', { description: (caught as Error).message })
    } finally {
      setApplying(false)
    }
  }

  const cut = async (id: string) => {
    if (phase.step !== 'done') return
    setCutting(id)
    try {
      const compile = await api.cutCV(phase.result.slug, id)
      setPhase({ ...phase, result: { ...phase.result, compile } })
      void refresh()
    } catch (caught) {
      toast.error('Coupe impossible', { description: (caught as Error).message })
    } finally {
      setCutting(null)
    }
  }

  const current = phase.step === 'running' ? 'form' : phase.step

  return (
    <div className="flex h-full flex-col">
      <header className="flex h-11 shrink-0 items-center gap-3 border-b px-5">
        <h1 className="text-[13px] font-semibold tracking-tight">Cibler une offre</h1>
        <ol className="ml-auto flex items-center gap-1 text-[11.5px]" aria-label="Étapes">
          {STEPS.map(([key, label], i) => (
            <li key={key} className="flex items-center gap-1">
              {i > 0 && <span className="text-muted-foreground/50">›</span>}
              <span
                aria-current={current === key ? 'step' : undefined}
                className={cn('rounded px-1.5 py-0.5', current === key ? 'bg-muted font-medium text-foreground' : 'text-muted-foreground')}
              >
                {label}
              </span>
            </li>
          ))}
        </ol>
      </header>

      <div className="min-h-0 flex-1">
        {phase.step === 'review' && decisions ? (
          <Review
            draft={phase.draft}
            decisions={decisions}
            onChange={setDecisions}
            name={name}
            onName={setName}
            onApply={() => void apply(phase.draft)}
            onDiscard={discard}
            onRerun={() => void rerun(phase.draft)}
            applying={applying}
          />
        ) : (
          <ScrollArea className="h-full">
            {phase.step === 'form' && (
              <div className="mx-auto flex max-w-3xl flex-col gap-4 px-6 py-8">
                {error && (
                  <div role="alert" className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-[12.5px]">
                    <CircleAlert className="mt-px size-4 shrink-0 text-destructive" />
                    <span className="flex-1">{error}</span>
                    <button type="button" onClick={() => setError(null)} aria-label="Fermer" className="text-muted-foreground hover:text-foreground">
                      <X className="size-3.5" />
                    </button>
                  </div>
                )}
                <OfferForm
                  cvs={cvs}
                  value={form}
                  onChange={setForm}
                  onSubmit={(request) => void start(request)}
                  openSettings={() => navigate({ view: 'settings' })}
                />
              </div>
            )}
            {phase.step === 'running' && (
              <div className="px-6">
                <ProgressPanel run={phase.run} onCancel={() => abort.current?.abort()} />
              </div>
            )}
            {phase.step === 'done' && (
              <ResultPanel
                result={phase.result}
                name={name}
                keywords={phase.draft.analysis.keywords}
                libraryAdded={phase.result.library_added}
                cutting={cutting}
                onCut={(id) => void cut(id)}
                onOpen={() => navigate({ view: 'cv', slug: phase.result.slug })}
                onAgain={() => {
                  setForm({ ...form, text: '', url: '' })
                  setPhase({ step: 'form' })
                }}
              />
            )}
          </ScrollArea>
        )}
      </div>
    </div>
  )
}
