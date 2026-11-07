import { Check, Copy, Download, Lightbulb, Loader2, RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetTitle } from '@/components/ui/sheet'
import { api } from '@/lib/api'
import type { OfferAnalysis, ProjectIdea } from '@/lib/types'

/** Trois projets à faire soi-même, qui rendent vrais les mots-clés de l'offre qui manquent au CV. */
export function ProjectIdeas({ slug, analysis }: { slug: string; analysis: OfferAnalysis }) {
  const [ideas, setIdeas] = useState<ProjectIdea[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [open, setOpen] = useState<number | null>(null)

  useEffect(() => {
    api.projectIdeas(slug).then(
      (saved) => setIdeas(saved.ideas),
      () => setIdeas([]),
    )
  }, [slug])

  const propose = async () => {
    setBusy(true)
    try {
      setIdeas((await api.proposeProjectIdeas(slug)).ideas)
    } catch (error) {
      toast.error('Pas d’idées cette fois', { description: (error as Error).message })
    } finally {
      setBusy(false)
    }
  }

  const has = (ideas?.length ?? 0) > 0
  return (
    <section aria-label="Idées de projet" className="flex flex-col gap-3 rounded-xl border bg-muted/30 p-4">
      <div className="flex flex-wrap items-start gap-3">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground">
          <Lightbulb className="size-4" />
        </span>
        <div className="flex min-w-60 flex-1 flex-col gap-0.5">
          <h3 className="text-[14px] font-semibold">Idées de projet</h3>
          <p className="max-w-[62ch] text-[12.5px] leading-relaxed text-foreground/80">
            L’astuce : un petit projet personnel, fait en quelques jours, qui rend <b>vrais</b> les mots-clés qui te manquent. Sur le CV, un
            recruteur fait tout de suite le lien avec son offre.
          </p>
        </div>
        {ideas !== null && (
          <Button size="sm" variant={has ? 'outline' : 'default'} className="h-8 gap-1.5 text-[12.5px]" disabled={busy} onClick={() => void propose()}>
            {busy ? <Loader2 className="size-3.5 animate-spin" /> : has ? <RefreshCw className="size-3.5" /> : <Lightbulb className="size-3.5" />}
            {has ? 'Proposer d’autres idées' : 'Proposer 3 idées'} · 1 requête
          </Button>
        )}
      </div>

      {busy && <p className="text-[12.5px] text-muted-foreground">L’IA cherche trois idées pour ce qui te manque… (environ 30 secondes)</p>}

      {has && (
        <div className="flex flex-col gap-2.5">
          {ideas!.map((idea, index) => (
            <article key={idea.name} className="flex flex-col gap-2.5 rounded-xl border bg-card surface p-4">
              <div className="flex flex-wrap items-center gap-2">
                <h4 className="flex-1 text-[14px] font-semibold">{idea.name}</h4>
                <span className="rounded-full bg-muted px-2 py-0.5 text-[11.5px] font-semibold text-foreground/80">{idea.effort}</span>
              </div>
              <p className="text-[13px] leading-relaxed">{idea.pitch}</p>
              <p className="text-[12.5px] leading-relaxed text-foreground/80">
                <b>Pour cette offre :</b> {idea.why}
              </p>
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-[11.5px] text-muted-foreground">Rend vrais :</span>
                {idea.keywords.map((keyword) => (
                  <span key={keyword} className="flex items-center gap-1 rounded-full bg-status-offer-soft px-2 py-0.5 text-[11.5px] font-semibold text-status-offer">
                    <Check className="size-3" />
                    {keyword}
                  </span>
                ))}
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-[11.5px] text-muted-foreground">Avec :</span>
                {idea.stack.map((tech) => (
                  <span key={tech} className="rounded-md border bg-background px-2 py-0.5 text-[11.5px]">
                    {tech}
                  </span>
                ))}
                <Button size="sm" className="ml-auto h-8 text-[12.5px]" onClick={() => setOpen(index)}>
                  Voir le cahier des charges
                </Button>
              </div>
            </article>
          ))}
          <p className="text-[12px] text-muted-foreground">Une fois le projet fait et publié sur GitHub, ajoute-le depuis la Bibliothèque : il pourra alors entrer dans tes CV.</p>
        </div>
      )}

      <Sheet open={open !== null} onOpenChange={(next) => !next && setOpen(null)}>
        {open !== null && ideas?.[open] && <Brief slug={slug} index={open} idea={ideas[open]} analysis={analysis} />}
      </Sheet>
    </section>
  )
}

function Brief({ slug, index, idea, analysis }: { slug: string; index: number; idea: ProjectIdea; analysis: OfferAnalysis }) {
  const url = api.projectBriefUrl(slug, index)
  const copy = async () => {
    try {
      const text = await (await fetch(url)).text()
      await navigator.clipboard.writeText(text)
      toast.success('Cahier des charges copié')
    } catch {
      toast.error('Copie impossible : télécharge le fichier.')
    }
  }
  const where = [analysis.company, analysis.location].filter(Boolean).join(' · ')
  const parts: [string, React.ReactNode][] = [
    ["L'offre visée", `${analysis.job_title}${where ? ` (${where})` : ''}.`],
    ['Ce que fait le projet', idea.pitch],
    ['Pourquoi il sert ta candidature', `Pour cette offre, ${idea.why}`],
    ["Mots-clés de l'offre qu'il rend vrais", `${idea.keywords.join(', ')}.`],
    [
      'Les composants',
      <ul key="m" className="list-disc pl-5">
        {idea.modules.map((m) => (
          <li key={m}>{m}</li>
        ))}
      </ul>,
    ],
    ['Les données', idea.data],
    [
      'Étapes',
      <ol key="s" className="list-decimal pl-5">
        {idea.steps.map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ol>,
    ],
    ['À livrer', 'Un dépôt public avec un README (ce que fait le projet, captures, chiffres mesurés), des tests, un lancement en une commande.'],
    [
      'En entretien',
      <ul key="q" className="list-disc pl-5">
        {idea.questions.map((q) => (
          <li key={q}>{q}</li>
        ))}
      </ul>,
    ],
  ]
  return (
    <SheetContent className="max-w-[560px]">
      <div className="flex flex-col gap-1 border-b px-5 pt-5 pr-14 pb-4">
        <span className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">Cahier des charges</span>
        <SheetTitle>{idea.name}</SheetTitle>
        <SheetDescription>
          {idea.effort} · {idea.stack.join(', ')}
        </SheetDescription>
        <div className="flex gap-2 pt-2">
          <Button size="sm" variant="outline" className="h-8 gap-1.5 text-[12.5px]" onClick={() => void copy()}>
            <Copy className="size-3.5" /> Copier
          </Button>
          <Button size="sm" variant="outline" className="h-8 gap-1.5 text-[12.5px]" asChild>
            <a href={url} download>
              <Download className="size-3.5" /> Télécharger (.md)
            </a>
          </Button>
        </div>
      </div>
      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-5 py-4 text-[13px] leading-relaxed">
        {parts.map(([title, body]) => (
          <section key={title} className="flex flex-col gap-1">
            <h4 className="text-[13px] font-semibold">{title}</h4>
            <div className="text-foreground/80">{body}</div>
          </section>
        ))}
        <section className="flex flex-col gap-1 rounded-lg bg-muted/60 p-3">
          <h4 className="text-[13px] font-semibold">Sur ton CV, une fois fait</h4>
          <p>
            <b>{idea.name}</b> · Projet personnel
          </p>
          <p className="text-foreground/80">{idea.cv_line}</p>
        </section>
      </div>
    </SheetContent>
  )
}
