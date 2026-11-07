import { ChevronDown, ExternalLink, Loader2, Sparkles } from 'lucide-react'
import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { routeHash } from '@/hooks/use-route'
import { api, ApiError } from '@/lib/api'
import type { OfferInfo } from '@/lib/types'

import { KeywordChips, ScoreLine } from './coverage'
import { ProjectIdeas } from './project-ideas'

/** L'onglet « Offre » d'un CV : l'offre visée et la couverture de ses mots-clés. */
interface OfferTabProps {
  slug: string
  pdfVersion: number | null
}

export function OfferTab({ slug, pdfVersion }: OfferTabProps) {
  const [info, setInfo] = useState<OfferInfo | null | undefined>(undefined)
  const [error, setError] = useState<string | null>(null)

  // Le score est recalculé sur le PDF : à chaque nouvelle compilation.
  useEffect(() => {
    let cancelled = false
    api.getOffer(slug).then(
      (found) => !cancelled && setInfo(found),
      (caught: Error) => {
        if (cancelled) return
        if (caught instanceof ApiError && caught.status === 404) setInfo(null)
        else setError(caught.message)
      },
    )
    return () => {
      cancelled = true
    }
  }, [slug, pdfVersion])

  const target = () => {
    window.location.hash = routeHash({ view: 'target', source: slug })
  }

  if (error) return <p className="p-6 text-[13px] text-destructive">{error}</p>
  if (info === undefined)
    return (
      <div className="flex justify-center p-10 text-muted-foreground">
        <Loader2 className="size-5 animate-spin" />
      </div>
    )
  if (info === null)
    return (
      <div className="flex h-full items-center justify-center p-8">
        <div className="flex max-w-xs flex-col items-center gap-3 text-center">
          <div className="flex size-10 items-center justify-center rounded-xl bg-muted text-muted-foreground">
            <Sparkles className="size-5" />
          </div>
          <p className="text-[13px] font-medium">Ce CV ne vise aucune offre</p>
          <p className="text-[12px] text-muted-foreground">
            Colle une offre : l'IA en crée une version adaptée, que tu relis avant qu'elle soit enregistrée.
          </p>
          <Button size="sm" onClick={target} className="gap-1.5">
            <Sparkles className="size-3.5" /> Cibler une offre à partir de ce CV
          </Button>
        </div>
      </div>
    )

  const { analysis } = info
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6 px-5 py-5">
      <div className="flex flex-col gap-1">
        <h2 className="text-[15px] font-semibold tracking-tight">{analysis.job_title}</h2>
        <p className="text-[12.5px] text-muted-foreground">
          {[analysis.company, analysis.location, analysis.contract].filter(Boolean).join(' · ')}
          {info.url && (
            <a href={info.url} target="_blank" rel="noreferrer" className="ml-2 inline-flex items-center gap-0.5 text-primary hover:underline">
              l'offre <ExternalLink className="size-3" />
            </a>
          )}
        </p>
      </div>

      {info.score && (
        <section className="flex flex-col gap-3">
          <h3 className="text-[12px] font-semibold">Mots-clés de l'offre dans le PDF</h3>
          <ScoreLine after={info.score.score} caption="Recalculé à chaque compilation, sur le texte que lira un logiciel de tri (ATS)." />
          <KeywordChips coverage={info.score} keywords={analysis.keywords} />
        </section>
      )}

      {info.missing.length > 0 && (
        <section className="flex flex-col gap-2">
          <h3 className="text-[12px] font-semibold">Ce que l'offre demande et que tu n'as pas</h3>
          <ul className="flex flex-col gap-1.5">
            {info.missing.map((m) => (
              <li key={m.term} className="text-[12px]">
                <span className="font-medium">{m.term}</span>
                {m.note && <span className="text-muted-foreground"> : {m.note}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}

      <ProjectIdeas slug={slug} analysis={analysis} />

      {info.text && (
        <Collapsible>
          <CollapsibleTrigger className="group flex items-center gap-1 text-[12px] font-semibold">
            <ChevronDown className="size-3.5 transition-transform group-data-[state=open]:rotate-180" />
            Texte de l'offre
          </CollapsibleTrigger>
          <CollapsibleContent>
            <p className="mt-2 rounded-lg border bg-muted/30 p-3 text-[12px] leading-relaxed whitespace-pre-wrap text-muted-foreground">
              {info.text}
            </p>
          </CollapsibleContent>
        </Collapsible>
      )}

      <Button variant="outline" size="sm" onClick={target} className="w-fit gap-1.5">
        <Sparkles className="size-3.5" /> Cibler une autre offre à partir de ce CV
      </Button>
    </div>
  )
}
