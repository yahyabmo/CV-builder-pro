import { AlertTriangle, Check, ChevronDown, Info, Loader2, PencilLine, Plus, RefreshCw, RotateCcw, Sparkles, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { api } from '@/lib/api'
import type { Change, ChangeGroup, Chip, Coverage, Draft } from '@/lib/types'
import { cn } from '@/lib/utils'

import { KeywordChips, ScoreLine } from './coverage'
import { acceptedTexts, changeText, chipShown, pendingCount, type Decisions } from './decisions'
import { DiffText } from './diff-text'

const GROUPS: ChangeGroup[] = ['En-tête', 'Compétences', 'Expérience', 'Projets', 'Langue']
const KIND = {
  replace: { label: 'Modifié', className: 'text-primary' },
  add: { label: 'Ajouté', className: 'text-success' },
  remove: { label: 'Retiré', className: 'text-destructive' },
}

interface ReviewProps {
  draft: Draft
  decisions: Decisions
  onChange: (decisions: Decisions) => void
  name: string
  onName: (name: string) => void
  onApply: () => void
  onDiscard: () => void
  onRerun: () => void
  applying: boolean
}

export function Review({ draft, decisions, onChange, name, onName, onApply, onDiscard, onRerun, applying }: ReviewProps) {
  const { analysis } = draft
  const total = draft.changes.length
  const kept = draft.changes.filter((c) => decisions.accepted[c.id]).length
  const waiting = pendingCount(draft, decisions)
  const empty = draft.changes.some(
    (c) => decisions.accepted[c.id] && c.kind !== 'remove' && c.id !== 'translation' && !changeText(c, decisions).trim(),
  )
  // Tout accepter n'accepte pas ce qui demande une confirmation : ça reste un clic par terme.
  const setAll = (value: boolean) =>
    onChange({
      ...decisions,
      accepted: Object.fromEntries(
        draft.changes.map((c) => [c.id, value ? (c.pending.length > 0 && c.group !== 'Compétences' ? decisions.accepted[c.id] : true) : false]),
      ),
    })

  // Le score suit les choix en direct (calcul local, sans IA).
  const [live, setLive] = useState<Coverage | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      const edits = decisions.accepted.translation ? decisions.translation : {}
      api.scoreDraft(draft.id, acceptedTexts(draft, decisions), edits, controller.signal).then(setLive, () => undefined)
    }, 300)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [draft, decisions])
  const coverage = live ?? draft.score_after

  // « Je l'ai » : ajouté à la bibliothèque, à reprendre en relançant.
  const [owned, setOwned] = useState<Set<string>>(new Set())
  const own = async (term: string) => {
    try {
      await api.addSkills(term, { source: 'offre' })
      setOwned(new Set([...owned, term]))
    } catch (error) {
      toast.error('Ajout impossible', { description: (error as Error).message })
    }
  }

  return (
    <div className="flex h-full flex-col lg:flex-row">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto [scrollbar-gutter:stable]">
        <div className="flex flex-col gap-5 px-6 py-6">
          <div className="flex flex-col gap-1">
            <p className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
              Proposition pour{draft.parent ? ' (relancée)' : ''}
            </p>
            <h2 className="text-xl font-semibold tracking-tight text-balance">{analysis.job_title || 'Offre sans intitulé'}</h2>
            <p className="text-[13px] text-muted-foreground">
              {[analysis.company, analysis.location, analysis.contract].filter(Boolean).join(' · ')}
              {draft.language !== draft.source_language && (
                <Badge variant="secondary" className="ml-2 h-5 text-[10.5px]">
                  CV en {draft.language === 'en' ? 'anglais' : 'français'}
                </Badge>
              )}
            </p>
          </div>

          {waiting > 0 && (
            <div className="flex items-start gap-2 rounded-lg border border-warning/40 bg-warning/5 p-3 text-[12.5px]">
              <AlertTriangle className="mt-px size-4 shrink-0 text-warning" />
              <span>
                <span className="font-medium">{waiting} élément{waiting > 1 ? 's' : ''} à confirmer</span>, en orange : ils
                ne sont pas dans ta bibliothèque. Coche ou clique ce qui est vrai pour toi ; à la création du CV, ça rejoindra ta
                bibliothèque.
              </span>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-2 text-[12.5px]">
            <span className="text-muted-foreground tabular-nums">
              {kept} changement{kept > 1 ? 's' : ''} accepté{kept > 1 ? 's' : ''} sur {total}
            </span>
            <span className="ml-auto flex gap-1">
              <Button variant="ghost" size="sm" className="h-7 text-[12px]" onClick={() => setAll(true)} title="Sauf ce qui demande une confirmation">
                Tout accepter
              </Button>
              <Button variant="ghost" size="sm" className="h-7 text-[12px]" onClick={() => setAll(false)}>
                Tout refuser
              </Button>
            </span>
          </div>

          {total === 0 && (
            <p className="rounded-lg border border-dashed p-6 text-center text-[13px] text-muted-foreground">
              Ton CV colle déjà à cette offre : l'IA ne propose aucun changement.
            </p>
          )}

          {GROUPS.map((group) => {
            const changes = draft.changes.filter((c) => c.group === group)
            if (changes.length === 0) return null
            return (
              <section key={group} className="flex flex-col gap-2" aria-label={group}>
                <h3 className="text-[12px] font-semibold tracking-wide text-muted-foreground uppercase">{group}</h3>
                {changes.map((change) => (
                  <ChangeCard key={change.id} change={change} draft={draft} decisions={decisions} onChange={onChange} />
                ))}
              </section>
            )
          })}
        </div>

        <div className="sticky bottom-0 mt-auto border-t bg-background/95 px-6 py-3 backdrop-blur">
          <div className="flex flex-wrap items-center gap-2">
            <Input
              value={name}
              onChange={(e) => onName(e.target.value)}
              className="h-8 max-w-xs flex-1 text-[13px]"
              aria-label="Nom du nouveau CV"
              placeholder="Nom du nouveau CV"
            />
            <Button onClick={onApply} disabled={applying || !name.trim() || empty} className="h-8 gap-1.5">
              {applying ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
              Créer le CV
            </Button>
            <Button variant="ghost" onClick={onDiscard} disabled={applying} className="h-8 gap-1.5 text-muted-foreground">
              <Trash2 className="size-3.5" /> Abandonner
            </Button>
            {empty && <span className="text-[12px] text-destructive">Un changement accepté est vide : complète-le ou refuse-le.</span>}
          </div>
        </div>
      </div>

      <aside className="flex max-h-[40%] w-full shrink-0 flex-col gap-5 overflow-y-auto border-t bg-muted/30 px-5 py-6 lg:max-h-none lg:w-80 lg:border-t-0 lg:border-l">
        <section className="flex flex-col gap-3">
          <h3 className="text-[12px] font-semibold">Mots-clés de l'offre</h3>
          <ScoreLine
            before={draft.score_before.score}
            after={coverage.score}
            caption="Avec tes choix actuels. Recalculée sur le PDF une fois le CV créé."
          />
          <KeywordChips coverage={coverage} keywords={analysis.keywords} />
        </section>

        {draft.plan.missing.length > 0 && (
          <section className="flex flex-col gap-2">
            <h3 className="text-[12px] font-semibold">Ce que l'offre demande et que tu n'as pas</h3>
            <ul className="flex flex-col gap-2">
              {draft.plan.missing.map((m) => (
                <li key={m.term} className="flex items-start gap-2 text-[12px]">
                  <span className="min-w-0 flex-1">
                    <span className="font-medium">{m.term}</span>
                    {m.note && <span className="text-muted-foreground"> : {m.note}</span>}
                  </span>
                  {owned.has(m.term) ? (
                    <span className="flex shrink-0 items-center gap-0.5 text-[11px] text-success"><Check className="size-3" /> ajouté</span>
                  ) : (
                    <Button variant="outline" size="sm" className="h-6 shrink-0 gap-0.5 px-1.5 text-[11px]" onClick={() => void own(m.term)} title="Ajouter à ta bibliothèque">
                      <Plus className="size-3" /> Je l'ai
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}

        <section className="flex flex-col gap-1.5">
          <Button variant={owned.size ? 'default' : 'outline'} size="sm" className="h-8 gap-1.5 text-[12px]" onClick={onRerun} disabled={applying}>
            <RefreshCw className="size-3.5" /> Relancer avec ma bibliothèque
          </Button>
          <p className="text-[11px] text-muted-foreground">
            Refait le choix et les formulations, sans réanalyser l'offre (2 requêtes{draft.language !== draft.source_language ? ', 3 avec la traduction' : ''}).
            Tes choix sont repris quand ils s'appliquent encore.
          </p>
        </section>

        {draft.plan.projects.length > 0 && (
          <section className="flex flex-col gap-2">
            <h3 className="text-[12px] font-semibold">Projets retenus, dans l'ordre</h3>
            <ol className="flex list-decimal flex-col gap-1.5 pl-4">
              {draft.plan.projects.map((p) => (
                <li key={p.id} className="text-[12px]">
                  <span className="font-medium">{draft.projects[p.id]?.title ?? p.id}</span>
                  {p.reason && <span className="block text-muted-foreground">{p.reason}</span>}
                </li>
              ))}
            </ol>
          </section>
        )}

        {analysis.summary && (
          <section className="flex flex-col gap-1.5">
            <h3 className="text-[12px] font-semibold">Le poste en bref</h3>
            <p className="text-[12px] text-muted-foreground">{analysis.summary}</p>
          </section>
        )}

        <p className="mt-auto text-[11px] text-muted-foreground/80 tabular-nums">
          {draft.model} · {String(draft.seconds).replace('.', ',')} s ·{' '}
          {((draft.tokens.input ?? 0) + (draft.tokens.output ?? 0)).toLocaleString('fr')} jetons
        </p>
      </aside>
    </div>
  )
}

interface CardProps {
  change: Change
  draft: Draft
  decisions: Decisions
  onChange: (decisions: Decisions) => void
}

function ChangeCard({ change, draft, decisions, onChange }: CardProps) {
  const [editing, setEditing] = useState(false)
  const accepted = decisions.accepted[change.id] ?? false
  const text = decisions.texts[change.id] ?? change.after
  const edited = decisions.texts[change.id] != null && decisions.texts[change.id] !== change.after
  const isSkills = change.chips.length > 0 && change.kind !== 'remove'
  const editable = change.kind !== 'remove' && change.id !== 'translation' && !isSkills
  const asks = change.pending.length > 0 && !isSkills
  const kind = KIND[change.kind]

  const setText = (value: string | null) => {
    const texts = { ...decisions.texts }
    if (value == null) delete texts[change.id]
    else texts[change.id] = value
    onChange({ ...decisions, texts })
  }

  return (
    <article
      className={cn(
        'flex flex-col gap-2 rounded-lg border bg-card surface p-3 transition-opacity',
        !accepted && 'opacity-60',
        asks && 'border-warning/50',
      )}
    >
      <header className="flex items-start gap-2.5">
        <Checkbox
          checked={accepted}
          onCheckedChange={(value) => onChange({ ...decisions, accepted: { ...decisions.accepted, [change.id]: value === true } })}
          aria-label={`Accepter : ${change.label}`}
          className="mt-0.5"
        />
        <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-2">
          <span className="text-[13px] font-medium">{change.label}</span>
          <span className={cn('text-[11px] font-medium', kind.className)}>{kind.label}</span>
          {asks && <span className="text-[11px] font-medium text-warning">à confirmer</span>}
          {edited && <span className="text-[11px] text-muted-foreground">· retouché</span>}
        </div>
        {editable && (
          <Button
            variant="ghost"
            size="sm"
            className="-my-1 h-7 gap-1 px-2 text-[11.5px] text-muted-foreground"
            onClick={() => setEditing(!editing)}
            aria-expanded={editing}
          >
            <PencilLine className="size-3.5" /> {editing ? 'Fermer' : 'Retoucher'}
          </Button>
        )}
      </header>

      <div className="pl-6.5">
        {change.id === 'translation' ? (
          <TranslationList draft={draft} decisions={decisions} onChange={onChange} />
        ) : isSkills ? (
          <ChipEditor change={change} decisions={decisions} onChange={onChange} />
        ) : editing ? (
          <div className="flex flex-col gap-1.5">
            <Textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              className="min-h-20 text-[13px] leading-relaxed"
              aria-label={`Texte de ${change.label}`}
              autoFocus
            />
            {change.lines.length > 0 && <p className="text-[11.5px] text-muted-foreground">Une puce par ligne.</p>}
            {edited && (
              <button
                type="button"
                className="flex w-fit items-center gap-1 text-[11.5px] text-muted-foreground hover:text-foreground"
                onClick={() => setText(null)}
              >
                <RotateCcw className="size-3" /> Revenir à la proposition
              </button>
            )}
          </div>
        ) : change.lines.length > 0 ? (
          <Lines change={change} text={text} edited={edited} />
        ) : change.kind === 'replace' ? (
          <DiffText before={change.before} after={text} />
        ) : change.kind === 'add' ? (
          <p className="text-[13px] leading-relaxed">
            <ins className="rounded-sm bg-success/15 no-underline">{text}</ins>
          </p>
        ) : (
          <p className="text-[13px] leading-relaxed">
            <del className="text-muted-foreground decoration-destructive/50">{change.before}</del>
          </p>
        )}

        {(change.warnings.length > 0 || change.notes.length > 0) && (
          <ul className="mt-2 flex flex-col gap-1">
            {change.warnings.map((w) => (
              <li key={w} className="flex items-start gap-1.5 text-[12px] text-warning">
                <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
                <span className="text-foreground/90">{w}</span>
              </li>
            ))}
            {change.notes.map((n) => (
              <li key={n} className="flex items-start gap-1.5 text-[12px] text-muted-foreground">
                <Info className="mt-0.5 size-3.5 shrink-0" />
                {n}
              </li>
            ))}
          </ul>
        )}
      </div>
    </article>
  )
}

const CHIP_STYLE: Record<Chip['state'], [shown: string, hidden: string]> = {
  kept: ['border-border bg-background', 'border-dashed text-muted-foreground line-through'],
  added: ['border-success/40 bg-success/10', 'border-dashed text-muted-foreground line-through'],
  pending: ['border-warning bg-warning/15 font-medium', 'border-dashed border-warning/70 text-foreground/80'],
  removed: ['border-border bg-background', 'border-dashed text-muted-foreground line-through'],
}

const CHIP_TITLE: Record<Chip['state'], string> = {
  kept: 'Déjà dans ce groupe',
  added: 'De ton profil, ajoutée à ce groupe',
  pending: "Pas dans ta bibliothèque : clique si tu l'as",
  removed: 'Retirée du CV : clique pour la garder',
}

/** Les compétences d'un groupe, chacune ajoutée ou retirée d'un clic. */
function ChipEditor({ change, decisions, onChange }: Omit<CardProps, 'draft'>) {
  const toggle = (chip: Chip) =>
    onChange({
      ...decisions,
      chips: { ...decisions.chips, [change.id]: { ...decisions.chips[change.id], [chip.text]: !chipShown(decisions, change, chip) } },
    })
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-1">
        {change.chips.map((chip) => {
          const shown = chipShown(decisions, change, chip)
          return (
            <button
              key={chip.text}
              type="button"
              onClick={() => toggle(chip)}
              aria-pressed={shown}
              title={CHIP_TITLE[chip.state]}
              className={cn(
                'inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[12px] transition-colors hover:border-ring/60',
                CHIP_STYLE[chip.state][shown ? 0 : 1],
              )}
            >
              {chip.state === 'pending' && (shown ? <Check className="size-3 text-warning" /> : <Plus className="size-3 text-warning" />)}
              {chip.text}
            </button>
          )
        })}
      </div>
      <p className="text-[11px] text-muted-foreground">
        Vert : de ton profil, ajoutée ici. Orange : à confirmer, clique si tu l'as. Barré : hors du CV, clique pour la garder.
      </p>
    </div>
  )
}

/** Les puces d'une expérience : adaptées, tirées de la réserve, retirées. */
function Lines({ change, text, edited }: { change: Change; text: string; edited: boolean }) {
  const used = new Set(change.lines.map((line) => line.source))
  const dropped = change.before.split('\n').filter((bullet) => bullet && !used.has(bullet))
  if (edited) {
    return (
      <ul className="flex list-disc flex-col gap-1 pl-4 text-[13px] leading-relaxed">
        {text.split('\n').filter(Boolean).map((line, i) => <li key={i}>{line}</li>)}
      </ul>
    )
  }
  return (
    <div className="flex flex-col gap-1.5">
      <ul className="flex flex-col gap-1.5">
        {change.lines.map((line, i) => (
          <li key={i} className="flex items-start gap-2">
            <span className="mt-2 size-1 shrink-0 rounded-full bg-muted-foreground/60" />
            <div className="min-w-0 flex-1">
              <DiffText before={line.source} after={line.text} />
              {line.reserve && <Badge variant="outline" className="mt-0.5 h-4 border-primary/40 px-1 text-[10px] font-normal text-primary">de ta réserve</Badge>}
            </div>
          </li>
        ))}
      </ul>
      {dropped.length > 0 && (
        <div className="flex flex-col gap-0.5">
          <p className="text-[11px] text-muted-foreground">Retirées de ce CV (elles restent dans ta bibliothèque) :</p>
          {dropped.map((bullet) => (
            <del key={bullet} className="text-[12px] text-muted-foreground decoration-destructive/40">{bullet}</del>
          ))}
        </div>
      )}
    </div>
  )
}

function TranslationList({ draft, decisions, onChange }: Omit<CardProps, 'change'>) {
  const paths = Object.keys(draft.translation)
  return (
    <Collapsible>
      <p className="text-[12.5px] text-muted-foreground">
        Titres de rubrique, formation, langues, centres d'intérêt… : tout ce que l'IA n'a pas déjà adapté plus haut.
      </p>
      <CollapsibleTrigger className="group mt-1.5 flex items-center gap-1 text-[12px] font-medium text-primary">
        <ChevronDown className="size-3.5 transition-transform group-data-[state=open]:rotate-180" />
        Relire les {paths.length} traductions
      </CollapsibleTrigger>
      <CollapsibleContent>
        <ul className="mt-2 flex flex-col divide-y rounded-md border">
          {paths.map((path) => (
            <li key={path} className="grid gap-1 p-2 sm:grid-cols-2 sm:gap-3">
              <span className="text-[12px] text-muted-foreground">{draft.translation_source[path]}</span>
              <Input
                value={decisions.translation[path] ?? draft.translation[path]}
                onChange={(e) => onChange({ ...decisions, translation: { ...decisions.translation, [path]: e.target.value } })}
                className="h-7 text-[12px]"
                aria-label={`Traduction de « ${draft.translation_source[path]} »`}
              />
            </li>
          ))}
        </ul>
      </CollapsibleContent>
    </Collapsible>
  )
}
