import { AlertTriangle, BookMarked, CheckCircle2, CircleAlert, FileText, Loader2, Scissors, Sparkles } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import type { ApplyResult, Keyword } from '@/lib/types'

import { KeywordChips, ScoreLine } from './coverage'

// Une ligne de texte du CV fait environ 12 pt.
const LINE_PT = 12

interface ResultPanelProps {
  result: ApplyResult
  name: string
  keywords: Keyword[]
  // Termes confirmés, ajoutés à la bibliothèque.
  libraryAdded: string[]
  cutting: string | null
  onCut: (id: string) => void
  onOpen: () => void
  onAgain: () => void
}

export function ResultPanel({ result, name, keywords, libraryAdded, cutting, onCut, onOpen, onAgain }: ResultPanelProps) {
  const { compile, score, slug } = result
  const fits = compile.ok && compile.pages === 1 && compile.overflow_pt <= 0.5
  const lines = Math.max(1, Math.ceil(compile.overflow_pt / LINE_PT))

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-6 py-8 sm:flex-row sm:items-start">
      <button
        type="button"
        onClick={onOpen}
        className="w-44 shrink-0 overflow-hidden rounded-lg border bg-white shadow-sm transition-shadow hover:shadow-md"
        aria-label={`Ouvrir ${name}`}
      >
        {compile.pdf_version ? (
          <img src={api.thumbnailUrl(slug, compile.pdf_version)} alt="" className="aspect-[1/1.4142] w-full object-cover object-top" />
        ) : (
          <span className="flex aspect-[1/1.4142] items-center justify-center text-muted-foreground">
            <FileText className="size-6" />
          </span>
        )}
      </button>

      <div className="flex min-w-0 flex-1 flex-col gap-5">
        <div className="flex flex-col gap-1">
          <p className="flex items-center gap-1.5 text-[12px] font-medium text-success">
            <CheckCircle2 className="size-4" /> CV créé
          </p>
          <h2 className="text-xl font-semibold tracking-tight text-balance">{name}</h2>
        </div>

        {!compile.ok ? (
          <div className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-[12.5px]">
            <CircleAlert className="mt-px size-4 shrink-0 text-destructive" />
            <span>La compilation a échoué : {compile.errors[0]?.message ?? 'erreur inconnue'}. Ouvre le CV pour corriger.</span>
          </div>
        ) : fits ? (
          <p className="flex items-center gap-1.5 text-[13px]">
            <CheckCircle2 className="size-4 text-success" /> Tient sur une page.
          </p>
        ) : (
          <div className="flex flex-col gap-2.5 rounded-lg border border-warning/40 bg-warning/5 p-3">
            <p className="flex items-start gap-2 text-[13px]">
              <AlertTriangle className="mt-px size-4 shrink-0 text-warning" />
              {compile.pages != null && compile.pages > 1
                ? `Le CV fait ${compile.pages} pages.`
                : `Le contenu dépasse le bas de la page d'environ ${lines} ligne${lines > 1 ? 's' : ''}.`}
            </p>
            {compile.cuts.length > 0 ? (
              <ul className="flex flex-col gap-1.5">
                {compile.cuts.map((cut) => (
                  <li key={cut.id} className="flex items-start gap-2 rounded-md bg-background p-2">
                    <div className="min-w-0 flex-1">
                      <p className="text-[12.5px] font-medium">{cut.label}</p>
                      <p className="truncate text-[11.5px] text-muted-foreground">{cut.detail}</p>
                    </div>
                    <Button size="sm" variant="outline" className="h-7 gap-1 text-[12px]" disabled={cutting != null} onClick={() => onCut(cut.id)}>
                      {cutting === cut.id ? <Loader2 className="size-3.5 animate-spin" /> : <Scissors className="size-3.5" />}
                      Couper
                    </Button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[12px] text-muted-foreground">Ouvre le CV pour raccourcir un texte ou masquer une section.</p>
            )}
          </div>
        )}

        {libraryAdded.length > 0 && (
          <p className="flex items-start gap-1.5 text-[12.5px]">
            <BookMarked className="mt-0.5 size-4 shrink-0 text-primary" />
            <span>
              Ajouté à ta bibliothèque : <span className="font-medium">{libraryAdded.join(', ')}</span>
            </span>
          </p>
        )}

        {score && (
          <section className="flex flex-col gap-3">
            <h3 className="text-[12px] font-semibold">Mots-clés de l'offre dans le PDF</h3>
            <ScoreLine after={score.score} caption="Mesuré sur le texte que lira un logiciel de tri (ATS)." />
            <KeywordChips coverage={score} keywords={keywords} />
          </section>
        )}

        <div className="flex flex-wrap gap-2 border-t pt-5">
          <Button onClick={onOpen} className="gap-1.5">
            <FileText className="size-4" /> Ouvrir le CV
          </Button>
          <Button variant="outline" onClick={onAgain} className="gap-1.5">
            <Sparkles className="size-4" /> Cibler une autre offre
          </Button>
        </div>
      </div>
    </div>
  )
}
