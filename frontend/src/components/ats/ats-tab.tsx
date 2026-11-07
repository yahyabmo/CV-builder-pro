import { CheckCircle2, ChevronDown, CircleAlert, Loader2, ScanSearch, TriangleAlert } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Input } from '@/components/ui/input'
import { api, ApiError } from '@/lib/api'
import type { AtsCheck, AtsReport, TermsResult } from '@/lib/types'
import { cn } from '@/lib/utils'

const ICON = {
  ok: <CheckCircle2 className="size-4 text-success" />,
  warn: <TriangleAlert className="size-4 text-warning" />,
  fail: <CircleAlert className="size-4 text-destructive" />,
} satisfies Record<AtsCheck['status'], React.ReactNode>

/** L'onglet « ATS » : ce qu'un logiciel de tri lit dans le PDF, vérifié. */
export function AtsTab({ slug, pdfVersion }: { slug: string; pdfVersion: number | null }) {
  const [report, setReport] = useState<AtsReport | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [terms, setTerms] = useState('')
  const [checked, setChecked] = useState<TermsResult | null>(null)
  const [checking, setChecking] = useState(false)
  const [offerTerms, setOfferTerms] = useState<string[]>([])

  // Refait à chaque nouvelle compilation.
  useEffect(() => {
    let cancelled = false
    api.ats(slug).then(
      (found) => {
        if (cancelled) return
        setReport(found)
        setError(null)
      },
      (caught: Error) => !cancelled && setError(caught.message),
    )
    return () => {
      cancelled = true
    }
  }, [slug, pdfVersion])

  // Un CV ciblé : ses mots-clés d'offre à tester d'un clic.
  useEffect(() => {
    api.getOffer(slug).then(
      (offer) => setOfferTerms(offer.analysis.keywords.map((k) => k.term)),
      (caught: Error) => caught instanceof ApiError && caught.status === 404 && setOfferTerms([]),
    )
  }, [slug])

  const test = async (text: string) => {
    const list = text.split(/[,;\n]+/).map((t) => t.trim()).filter(Boolean)
    if (!list.length) return
    setChecking(true)
    try {
      setChecked(await api.atsTerms(slug, list))
    } catch (caught) {
      setError((caught as Error).message)
    } finally {
      setChecking(false)
    }
  }

  if (error && !report) return <p className="p-6 text-[13px] text-destructive">{error}</p>
  if (!report)
    return (
      <div className="flex justify-center p-10 text-muted-foreground">
        <Loader2 className="size-5 animate-spin" />
      </div>
    )

  const ok = report.checks.filter((c) => c.status === 'ok').length
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6 px-5 py-5">
      <div className="flex flex-col gap-1">
        <h2 className="text-[15px] font-semibold tracking-tight">Ce que lit un logiciel de tri</h2>
        <p className="text-[12.5px] text-muted-foreground">
          Un ATS ne voit pas la mise en page, seulement le texte extrait du PDF. {ok} vérification{ok > 1 ? 's' : ''} sur{' '}
          {report.checks.length} au vert.
        </p>
      </div>

      <ul className="flex flex-col divide-y rounded-lg border bg-card surface">
        {report.checks.map((check) => (
          <li key={check.id} className="flex items-start gap-2.5 px-3 py-2.5">
            <span className="mt-px">{ICON[check.status]}</span>
            <div className="min-w-0">
              <p className="text-[13px] font-medium">{check.label}</p>
              <p className="text-[12px] text-muted-foreground">{check.detail}</p>
              {check.id === 'words' && report.words.missing.length > 0 && (
                <p className="mt-1 flex flex-wrap gap-1">
                  {report.words.missing.map((w) => (
                    <span key={w} className="rounded border border-dashed px-1.5 text-[11px] text-muted-foreground">{w}</span>
                  ))}
                </p>
              )}
            </div>
          </li>
        ))}
      </ul>

      <section className="flex flex-col gap-2">
        <h3 className="text-[12px] font-semibold">Tester des mots-clés</h3>
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            void test(terms)
          }}
        >
          <Input
            value={terms}
            onChange={(e) => setTerms(e.target.value)}
            placeholder="Python, Kubernetes, revue de code…"
            className="h-8 text-[12.5px]"
            aria-label="Mots-clés à chercher dans le PDF"
          />
          <Button type="submit" size="sm" className="h-8 gap-1.5 text-[12px]" disabled={checking || !terms.trim()}>
            {checking ? <Loader2 className="size-3.5 animate-spin" /> : <ScanSearch className="size-3.5" />} Chercher
          </Button>
        </form>
        {offerTerms.length > 0 && (
          <button
            type="button"
            className="w-fit text-[12px] text-primary hover:underline"
            onClick={() => {
              const all = offerTerms.join(', ')
              setTerms(all)
              void test(all)
            }}
          >
            Tester les mots-clés de l'offre visée
          </button>
        )}
        {checked && (
          <div className="flex flex-wrap gap-1">
            {checked.present.map((t) => (
              <span key={t} className="rounded-md border border-success/30 bg-success/10 px-1.5 py-0.5 text-[11.5px]">{t}</span>
            ))}
            {checked.absent.map((t) => (
              <span key={t} className="rounded-md border border-dashed px-1.5 py-0.5 text-[11.5px] text-muted-foreground line-through">{t}</span>
            ))}
          </div>
        )}
      </section>

      <Collapsible>
        <CollapsibleTrigger className="group flex items-center gap-1 text-[12px] font-semibold">
          <ChevronDown className="size-3.5 transition-transform group-data-[state=open]:rotate-180" />
          Le texte tel qu'un ATS le reçoit
        </CollapsibleTrigger>
        <CollapsibleContent>
          <ExtractedText text={report.text} highlight={checked?.present ?? []} />
        </CollapsibleContent>
      </Collapsible>
    </div>
  )
}

function ExtractedText({ text, highlight }: { text: string; highlight: string[] }) {
  // Les mots-clés trouvés, surlignés (sans tenir compte de la casse).
  const parts = useMemo(() => {
    const terms = highlight.filter((t) => t.length > 1).map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
    if (!terms.length) return [text]
    return text.split(new RegExp(`(${terms.join('|')})`, 'gi'))
  }, [text, highlight])
  return (
    <pre className="mt-2 max-h-96 overflow-auto rounded-lg border bg-muted/30 p-3 font-mono text-[11.5px] leading-relaxed whitespace-pre-wrap">
      {parts.map((part, i) => (
        <span key={i} className={cn(i % 2 === 1 && 'rounded-sm bg-success/20')}>{part}</span>
      ))}
    </pre>
  )
}
