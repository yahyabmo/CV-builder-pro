import { Plus, TriangleAlert } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { CvEditor } from '@/hooks/use-cv-editor'
import { api } from '@/lib/api'
import type { CVContent, OfferInfo, PageLocation } from '@/lib/types'
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

interface AddKeywordProps {
  term: string
  // L'analyse de l'offre l'a rangé dans ce que la personne n'a pas.
  lacking: boolean
  note: string | null
  content: CVContent
  update: CvEditor['update']
  onReveal: (location: PageLocation) => void
}

function AddKeyword({ term, lacking, note, content, update, onReveal }: AddKeywordProps) {
  const [open, setOpen] = useState(false)
  const groups = content.sections.flatMap((section) =>
    section.kind === 'skills' ? section.items.map((item, index) => ({ section, index, label: item.label })) : [],
  )

  const add = (sectionId: string, index: number, label: string) => {
    update((draft) => {
      const section = draft.sections.find((s) => s.id === sectionId)
      if (section?.kind === 'skills' && section.items[index]) section.items[index].text = appendTerm(section.items[index].text, term)
    })
    setOpen(false)
    onReveal(at(sectionId, index))
    toast.success(`« ${term} » ajouté à « ${label || 'Compétences'} »`, { description: 'Le score se met à jour à la prochaine compilation.' })
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
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
        className="flex w-72 flex-col gap-2.5 p-3"
        // Le curseur va dans le champ du groupe, pas sur le mot-clé.
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
          <p className="text-[12px] text-muted-foreground">Ajoute-le seulement si tu le maîtrises vraiment : il te sera demandé en entretien.</p>
        )}
        {groups.length > 0 ? (
          <div className="flex flex-col gap-1">
            <p className="text-[11.5px] font-medium text-muted-foreground">L'ajouter à un groupe de compétences :</p>
            {groups.map(({ section, index, label }) => (
              <button
                key={`${section.id}/${index}`}
                type="button"
                onClick={() => add(section.id, index, label)}
                className="flex items-center justify-between gap-2 rounded-md border px-2 py-1.5 text-left text-[12.5px] transition-colors hover:bg-accent"
              >
                <span className="truncate">{label || 'Groupe sans titre'}</span>
                <Plus className="size-3.5 shrink-0 text-muted-foreground" />
              </button>
            ))}
          </div>
        ) : (
          <p className="text-[12px] text-muted-foreground">Ce CV n'a pas de rubrique de compétences : ajoute-la dans l'onglet Contenu.</p>
        )}
      </PopoverContent>
    </Popover>
  )
}
