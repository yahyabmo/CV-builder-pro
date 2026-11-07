import { AlertCircle, Check, FileText, Loader2, Upload } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import type { Route } from '@/hooks/use-route'
import { api } from '@/lib/api'
import type { ImportReading, SettingsInfo } from '@/lib/types'
import { cn } from '@/lib/utils'

import { FlowHeader } from './welcome-flow'

type Phase =
  | { step: 'idle' }
  | { step: 'reading'; name: string }
  | { step: 'sorting'; name: string; reading: ImportReading }
  | { step: 'failed'; message: string }

/** Étape 1 : le PDF est lu (texte, photo), puis l'IA range son contenu. */
export function ImportStep({ navigate }: { navigate: (route: Route) => void }) {
  const [phase, setPhase] = useState<Phase>({ step: 'idle' })
  const [over, setOver] = useState(false)
  const [settings, setSettings] = useState<SettingsInfo | null>(null)
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => {
    api.getSettings().then(setSettings, () => setSettings(null))
  }, [])
  const provider = settings?.ai.provider
  const missingKey = settings != null && provider != null && provider in settings.keys && !settings.keys[provider]

  const start = async (file: Blob, name: string) => {
    setPhase({ step: 'reading', name })
    try {
      const reading = await api.uploadImport(file, name)
      setPhase({ step: 'sorting', name, reading })
      await api.readImport(reading.id)
      navigate({ view: 'welcome', step: 'review', id: reading.id })
    } catch (error) {
      setPhase({ step: 'failed', message: error instanceof Error ? error.message : String(error) })
    }
  }
  const pick = (file: File | undefined) => {
    if (file) void start(file, file.name)
  }
  const sample = async () => {
    const response = await fetch(api.demoPdfUrl)
    void start(await response.blob(), 'cv-exemple.pdf')
  }

  const busy = phase.step === 'reading' || phase.step === 'sorting'
  return (
    <>
      <FlowHeader back={() => navigate({ view: 'welcome', step: 'home' })} current={0} />
      <main className="mx-auto flex max-w-[1000px] flex-wrap items-start gap-8 px-6 py-12">
        <section className="flex min-w-0 flex-[999_1_520px] flex-col gap-5">
          <div className="flex flex-col gap-2">
            <h1 className="text-[27px] font-semibold tracking-tight">Importe ton CV</h1>
            <p className="text-[15px] leading-relaxed text-muted-foreground">
              Un PDF exporté depuis Word, Canva, LaTeX ou un site de CV. L'appli en lit le texte, la photo s'il y en a une, puis range tout
              dans ses rubriques.
            </p>
          </div>

          {(missingKey || provider === 'demo') && phase.step === 'idle' && (
            <p role="note" className="rounded-lg border border-status-interview/30 bg-status-interview-soft px-3.5 py-2.5 text-[13px] text-status-interview">
              {provider === 'demo'
                ? 'Mode démo : seul le PDF d’exemple a une lecture enregistrée. Pour ton CV, choisis un modèle d’IA dans Réglages.'
                : 'Aucune clé d’IA n’est configurée : l’import ne pourra pas ranger ton CV. Choisis un modèle dans Réglages, ou remplis ton CV à la main.'}
            </p>
          )}

          {!busy && (
            <div
              onDragOver={(e) => {
                e.preventDefault()
                setOver(true)
              }}
              onDragLeave={() => setOver(false)}
              onDrop={(e) => {
                e.preventDefault()
                setOver(false)
                pick(e.dataTransfer.files[0])
              }}
              className={cn('rounded-2xl border-2 border-dashed bg-card transition-colors', over ? 'border-primary bg-primary/5' : 'border-primary/30')}
            >
              <button
                type="button"
                onClick={() => input.current?.click()}
                className="flex w-full flex-col items-center gap-3 rounded-2xl px-6 py-14 text-center focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
              >
                <span className="flex size-13 items-center justify-center rounded-2xl bg-status-sent-soft text-status-sent">
                  <Upload className="size-6" />
                </span>
                <span className="text-[16px] font-semibold">Dépose ton PDF ici</span>
                <span className="text-[13.5px] text-muted-foreground">
                  ou <span className="font-semibold text-primary underline underline-offset-2">choisis un fichier</span> · PDF, 10 Mo au plus
                </span>
              </button>
              <input ref={input} type="file" accept="application/pdf,.pdf" className="hidden" aria-label="Fichier PDF du CV" onChange={(e) => pick(e.target.files?.[0])} />
            </div>
          )}

          {!busy && (
            <button type="button" onClick={() => void sample()} className="self-start text-[13px] font-medium text-primary underline-offset-2 hover:underline">
              Essayer avec le PDF d'exemple
            </button>
          )}

          {phase.step === 'failed' && (
            <div role="alert" className="flex flex-col gap-3 rounded-xl border border-destructive/30 bg-destructive/5 p-4">
              <p className="flex items-start gap-2 text-[13.5px]">
                <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive" />
                {phase.message}
              </p>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" onClick={() => input.current?.click()}>
                  Choisir un autre PDF
                </Button>
                <Button size="sm" variant="ghost" onClick={() => navigate({ view: 'welcome', step: 'manual' })}>
                  Remplir à la main
                </Button>
              </div>
            </div>
          )}

          {busy && (
            <div className="flex flex-col gap-4 rounded-2xl border bg-card surface p-5" aria-live="polite">
              <div className="flex items-center gap-3">
                <span className="flex h-12 w-10 items-end justify-center rounded-md border bg-muted/40 pb-1 text-[9px] font-bold text-destructive">PDF</span>
                <div className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate text-[14px] font-semibold">{phase.name}</span>
                  <span className="text-[12.5px] text-muted-foreground">
                    {phase.step === 'sorting'
                      ? [phase.reading.pages && `${phase.reading.pages} page${phase.reading.pages > 1 ? 's' : ''}`, phase.reading.photo ? 'une photo trouvée' : 'pas de photo'].filter(Boolean).join(' · ')
                      : 'Envoi…'}
                  </span>
                </div>
              </div>
              <ol className="flex flex-col gap-3 text-[14px]">
                <Step state={phase.step === 'reading' ? 'running' : 'done'} text={phase.step === 'sorting' ? `Texte lu : ${phase.reading.words} mots` : 'Lecture du texte et de la photo…'} />
                <Step state={phase.step === 'sorting' ? 'running' : 'waiting'} text="L'IA range le contenu dans les rubriques de l'appli…" />
                <Step state="waiting" text="Relecture avant de valider" />
              </ol>
              <p className="border-t pt-3 text-[12.5px] text-muted-foreground">Une requête à l'IA, souvent moins d'une minute.</p>
            </div>
          )}
        </section>

        <aside className="flex flex-[1_1_300px] flex-col gap-3.5 rounded-2xl bg-muted/70 p-5">
          <h2 className="flex items-center gap-2 text-[14px] font-semibold">
            <FileText className="size-4" /> Ce que l'appli fait de ton PDF
          </h2>
          <ul className="flex list-disc flex-col gap-2.5 pl-4.5 text-[13.5px] leading-relaxed text-foreground/85">
            <li>Elle reprend ton texte tel quel : rien n'est réécrit, et tout mot absent de ton PDF est signalé.</li>
            <li>Ta mise en page n'est pas copiée : le CV prend le format de l'appli, propre et lisible par les logiciels de tri. Le style se règle ensuite.</li>
            <li>Tes compétences, expériences et projets entrent dans ta bibliothèque, déjà validés.</li>
          </ul>
          <p className="border-t pt-3 text-[12.5px] leading-relaxed text-muted-foreground">
            Un PDF scanné n'est qu'une image, sans texte à lire. L'appli te le dira et te proposera de remplir ton CV à la main.
          </p>
        </aside>
      </main>
    </>
  )
}

function Step({ state, text }: { state: 'done' | 'running' | 'waiting'; text: string }) {
  return (
    <li className={cn('flex items-center gap-2.5', state === 'running' && 'font-semibold', state === 'waiting' && 'text-muted-foreground')}>
      {state === 'done' && (
        <span className="flex size-5.5 items-center justify-center rounded-full bg-status-offer-soft text-status-offer">
          <Check className="size-3.5" />
        </span>
      )}
      {state === 'running' && <Loader2 className="size-5.5 animate-spin text-primary" />}
      {state === 'waiting' && <span className="size-5.5 rounded-full border" />}
      {text}
    </li>
  )
}
