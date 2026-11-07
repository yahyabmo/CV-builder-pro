import { ArrowRight, CheckCircle2, CircleAlert, ExternalLink, KeyRound, Loader2, ShieldCheck, Sparkles, Zap } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { KeyForm } from '@/components/setup/key-form'
import { MachineList, RecheckButton } from '@/components/setup/machine-checks'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { useMachine } from '@/hooks/use-machine'
import type { Route } from '@/hooks/use-route'
import { api } from '@/lib/api'
import { KEY_NAMES, keyed } from '@/lib/keys'
import type { AISettings, ConnectionTest, Provider, SettingsInfo } from '@/lib/types'
import { cn } from '@/lib/utils'

// Trois choix. Ollama (local) et Démo restent dans Réglages › Autres options, et le
// mode Démo s'ouvre aussi par le lien en bas de l'écran.
const CARDS: { id: Provider; name: string; badge?: string; text: string; facts: [string, string]; icon: typeof Sparkles }[] = [
  {
    id: 'relais',
    name: 'Gemini de Yahya',
    badge: 'Recommandé',
    text: 'Gratuit pour toi, sur invitation : le code d’accès que Yahya t’a donné suffit. Aucune clé à créer.',
    facts: ['Un code d’accès, rien d’autre', 'Environ 6 CV ciblés par jour'],
    icon: KeyRound,
  },
  {
    id: 'gemini',
    name: 'Gemini (ta clé)',
    text: 'Ta propre clé Google, gratuite avec un quota par jour. Le plus rapide pour cibler une offre.',
    facts: ['Clé gratuite en une minute', 'Environ 30 s par offre'],
    icon: Sparkles,
  },
  {
    id: 'mistral',
    name: 'Mistral (ta clé)',
    text: 'Entreprise française, payante à l’usage : quelques centimes par offre.',
    facts: ['Clé sur console.mistral.ai', 'Moyen de paiement demandé'],
    icon: Zap,
  },
]

const KEY_HELP: Record<'gemini' | 'mistral', { url: string; site: string; step: string }> = {
  gemini: { url: 'https://aistudio.google.com/apikey', site: 'Ouvre Google AI Studio', step: 'Clique sur « Create API key »' },
  mistral: { url: 'https://console.mistral.ai/api-keys', site: 'Ouvre la console Mistral', step: 'Crée une clé dans « API Keys »' },
}

const seconds = (s: number) => `${String(s).replace('.', ',')} s`

/** Le premier écran du premier lancement : le modèle d'IA, sa clé, et la machine. */
export function SetupStep({ navigate }: { navigate: (route: Route) => void }) {
  const [info, setInfo] = useState<SettingsInfo | null>(null)
  const [ai, setAi] = useState<AISettings | null>(null)
  const [replacing, setReplacing] = useState(false)
  const [test, setTest] = useState<ConnectionTest | null>(null)
  const [testing, setTesting] = useState(false)
  const [leaving, setLeaving] = useState(false)
  const machine = useMachine()

  useEffect(() => {
    api.getSettings().then(
      (next) => {
        setInfo(next)
        // Premier lancement, relais en service et pas de clé Gemini : « Gemini de Yahya » d'abord.
        const fresh = next.ai.provider === 'gemini' && !next.keys.gemini && next.relay_ready
        setAi(fresh ? { ...next.ai, provider: 'relais' } : next.ai)
      },
      (error: Error) => toast.error('Réglages indisponibles', { description: error.message }),
    )
  }, [])

  if (!info || !ai) {
    return (
      <div className="mx-auto flex max-w-[1040px] flex-col gap-6 px-6 pt-14">
        <Skeleton className="h-12 w-2/3 rounded-xl" />
        <Skeleton className="h-44 w-full rounded-xl" />
      </div>
    )
  }

  const provider = ai.provider
  const hasKey = keyed(provider) && info.keys[provider]
  const relayDown = provider === 'relais' && !info.relay_ready
  const ready = provider === 'demo' || (hasKey && !relayDown) || (provider === 'ollama' && test?.ok === true)
  const latexMissing = machine.machine?.checks.some((c) => c.id === 'latex' && c.ok === false)

  const pick = (next: Provider) => {
    setAi({ ...ai, provider: next })
    setTest(null)
    setReplacing(false)
  }

  /** Un essai du modèle choisi, réglages enregistrés d'abord (Ollama, ou une clé déjà là). */
  const runTest = async () => {
    setTesting(true)
    setTest(null)
    try {
      await api.saveSettings(ai)
      setTest(await api.testConnection())
    } catch (error) {
      setTest({ ok: false, model: '', seconds: 0, message: (error as Error).message })
    } finally {
      setTesting(false)
    }
  }

  const leave = async (choice: AISettings) => {
    setLeaving(true)
    try {
      await api.saveSettings(choice)
      await api.setupDone()
      navigate({ view: 'welcome', step: 'home' })
    } catch (error) {
      toast.error('Impossible de continuer', { description: (error as Error).message })
      setLeaving(false)
    }
  }

  const testLine = test && (
    <p role="status" className={cn('flex items-center gap-1.5 text-[13px]', test.ok ? 'text-status-offer' : 'text-destructive')}>
      {test.ok ? <CheckCircle2 className="size-4" /> : <CircleAlert className="size-4" />}
      {test.ok ? `${test.model} répond (${seconds(test.seconds)})` : test.message}
    </p>
  )

  return (
    <>
      <header className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-x-6 gap-y-3 border-b bg-card/95 px-6 py-3.5 backdrop-blur">
        <div className="flex items-center gap-2.5">
          <img src="/favicon.png" alt="" className="size-7.5" />
          <span className="text-[15px] font-semibold tracking-tight">CV Builder Pro</span>
        </div>
        <ol aria-label="Étapes" className="flex flex-wrap items-center gap-x-5 gap-y-2 text-[13px]">
          <li aria-current="step" className="flex items-center gap-2 font-semibold">
            <span className="flex size-5 items-center justify-center rounded-full bg-primary text-[11px] text-primary-foreground">1</span>Préparer l'appli
          </li>
          <li aria-hidden="true" className="h-px w-7 bg-input" />
          <li className="flex items-center gap-2 text-muted-foreground">
            <span className="flex size-5 items-center justify-center rounded-full border border-input text-[11px]">2</span>Ton CV de base
          </li>
        </ol>
        <span className="min-w-30 text-right text-[12px] text-muted-foreground">Une seule fois</span>
      </header>

      <div className="mx-auto flex max-w-[1040px] flex-col gap-9 px-6 pt-11 pb-10">
        <div className="flex max-w-[680px] flex-col gap-2.5">
          <h1 className="text-[34px] leading-tight font-semibold tracking-tight text-balance">Réglons l'essentiel avant de commencer.</h1>
          <p className="text-[15.5px] leading-relaxed text-muted-foreground">
            Deux minutes, une seule fois : le modèle d'IA qui lira ton CV et tes offres, et une vérification de ta machine. Tout se change ensuite dans
            Réglages.
          </p>
        </div>

        <section aria-labelledby="modele" className="flex flex-col gap-3.5">
          <div className="flex flex-col gap-1">
            <h2 id="modele" className="text-[17px] font-semibold">
              Le modèle d'IA
            </h2>
            <p className="text-[13.5px] text-muted-foreground">Il lit ton CV en PDF, cible chaque offre et écrit la lettre. Rien n'entre dans ton CV sans ton accord.</p>
          </div>

          <div role="radiogroup" aria-label="Modèle d'IA" className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-3">
            {CARDS.map((card) => {
              const on = provider === card.id
              const Icon = card.icon
              return (
                <button
                  key={card.id}
                  type="button"
                  role="radio"
                  aria-checked={on}
                  onClick={() => pick(card.id)}
                  className={cn(
                    'flex flex-col gap-2 rounded-xl border bg-card surface p-4 text-left transition-shadow focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none',
                    on ? 'border-primary/60 shadow-[0_0_0_3px] shadow-primary/14' : 'hover:border-foreground/20',
                  )}
                >
                  <span className="flex items-center justify-between gap-2">
                    <span className={cn('flex size-8.5 items-center justify-center rounded-[9px]', on ? 'bg-primary text-primary-foreground' : 'bg-muted text-foreground/80')}>
                      <Icon className="size-4.5" />
                    </span>
                    <span className="flex items-center gap-2">
                      {card.id === 'relais' && !info.relay_ready ? (
                        <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] font-semibold text-muted-foreground">Bientôt</span>
                      ) : (
                        card.badge && <span className="rounded-full bg-accent px-2 py-0.5 text-[11px] font-semibold text-accent-foreground">{card.badge}</span>
                      )}
                      <span
                        aria-hidden="true"
                        className={cn('flex size-4 items-center justify-center rounded-full', on ? 'border-[5px] border-primary' : 'border-[1.5px] border-input')}
                      />
                    </span>
                  </span>
                  <span className="text-[15px] font-semibold">{card.name}</span>
                  <span className="text-[13px] leading-normal text-muted-foreground">{card.text}</span>
                  <span className="mt-auto flex flex-col gap-1 border-t border-dashed pt-2.5 text-[12.5px] text-foreground/75">
                    <span>{card.facts[0]}</span>
                    <span>{card.facts[1]}</span>
                  </span>
                </button>
              )
            })}
          </div>

          <div className="flex flex-col gap-4 rounded-xl border bg-card surface px-6 py-5.5">
            {relayDown && (
              <div className="flex items-start gap-3.5">
                <span className="flex size-9 shrink-0 items-center justify-center rounded-[10px] bg-muted text-muted-foreground">
                  <KeyRound className="size-4.5" />
                </span>
                <div className="flex flex-col gap-1">
                  <h3 className="text-[15px] font-semibold">Le relais de Yahya n'est pas encore en service.</h3>
                  <p className="max-w-[640px] text-[13px] leading-relaxed text-muted-foreground">
                    En attendant, choisis ta propre clé Gemini : elle est gratuite et se crée en une minute.
                  </p>
                </div>
              </div>
            )}

            {keyed(provider) && !relayDown && hasKey && !replacing && (
              <div className="flex flex-col gap-3">
                <h3 className="text-[15px] font-semibold">{provider === 'relais' ? 'Ton code d’accès' : `Ta clé ${KEY_NAMES[provider]}`}</h3>
                <p className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[13px]">
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-status-offer-soft px-2.5 py-1 font-semibold text-status-offer">
                    <CheckCircle2 className="size-3.5" /> {provider === 'relais' ? 'Code enregistré' : 'Clé enregistrée'}
                  </span>
                  <span className="text-muted-foreground">{provider === 'relais' ? 'Il est' : 'Elle est'} dans le fichier .env de ce dossier.</span>
                </p>
                <div className="flex flex-wrap items-center gap-2">
                  <Button variant="outline" size="sm" onClick={() => void runTest()} disabled={testing} className="gap-1.5">
                    {testing && <Loader2 className="size-3.5 animate-spin" />} Tester
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => setReplacing(true)}>
                    Remplacer
                  </Button>
                </div>
                {testLine}
              </div>
            )}

            {provider === 'relais' && !relayDown && (!hasKey || replacing) && (
              <div className="flex flex-col gap-4">
                <h3 className="text-[15px] font-semibold">Ton code d’accès</h3>
                <p className="max-w-[680px] text-[13px] leading-relaxed text-muted-foreground">
                  Yahya donne un code à chaque personne qu'il invite. Colle le tien ci-dessous : l'appli le vérifie auprès de son relais, puis tu
                  entres directement dans l'appli.
                </p>
                <KeyForm
                  key={provider}
                  provider={provider}
                  onSaved={() => {
                    setReplacing(false)
                    void api.saveSettings(ai).then(setInfo)
                  }}
                />
                <p className="flex items-start gap-2 text-[12.5px] leading-relaxed text-muted-foreground">
                  <ShieldCheck className="mt-0.5 size-3.5 shrink-0" />
                  Ton CV et tes offres passent par le relais de Yahya puis par Google, qui ne s'en sert pas pour entraîner ses modèles. Le relais n'en garde
                  rien.
                </p>
              </div>
            )}

            {(provider === 'gemini' || provider === 'mistral') && (!hasKey || replacing) && (
              <div className="flex flex-col gap-4">
                <h3 className="text-[15px] font-semibold">Ta clé {KEY_NAMES[provider]}</h3>
                <ol className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-2.5 text-[13px]">
                  {[
                    <a key="site" href={KEY_HELP[provider].url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 font-medium text-primary hover:underline">
                      {KEY_HELP[provider].site}
                      <ExternalLink className="size-3.5" />
                    </a>,
                    <span key="step">{KEY_HELP[provider].step}</span>,
                    <span key="paste">Colle-la ci-dessous, puis vérifie</span>,
                  ].map((content, i) => (
                    <li key={i} className="flex items-center gap-2.5 rounded-[10px] bg-muted px-3 py-2.5">
                      <span className="flex size-5 shrink-0 items-center justify-center rounded-full border border-input bg-card text-[11px] font-semibold">{i + 1}</span>
                      {content}
                    </li>
                  ))}
                </ol>
                <KeyForm
                  key={provider}
                  provider={provider}
                  onSaved={() => {
                    setReplacing(false)
                    void api.saveSettings(ai).then(setInfo)
                  }}
                />
              </div>
            )}

            {provider === 'ollama' && (
              <div className="flex flex-col gap-3.5">
                <h3 className="text-[15px] font-semibold">Ollama sur ta machine</h3>
                <p className="text-[13px] leading-relaxed text-muted-foreground">
                  Installe Ollama depuis{' '}
                  <a href="https://ollama.com" target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
                    ollama.com
                  </a>
                  , puis télécharge le modèle avec <code className="rounded-md bg-muted px-1.5 py-0.5 font-mono text-[12.5px]">ollama pull {ai.ollama_model}</code>.
                </p>
                <div className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] items-end gap-3">
                  <label className="flex flex-col gap-1.5 text-[12.5px] font-medium">
                    Adresse
                    <Input value={ai.ollama_url} onChange={(e) => setAi({ ...ai, ollama_url: e.target.value })} className="h-10 font-mono text-[13px]" />
                  </label>
                  <label className="flex flex-col gap-1.5 text-[12.5px] font-medium">
                    Modèle
                    <Input value={ai.ollama_model} onChange={(e) => setAi({ ...ai, ollama_model: e.target.value })} className="h-10 font-mono text-[13px]" />
                  </label>
                  <Button
                    variant="outline"
                    onClick={() => void runTest()}
                    disabled={testing}
                    className="h-10.5 gap-1.5 justify-self-start border-primary/35 bg-accent px-4.5 font-semibold text-accent-foreground hover:bg-accent/70"
                  >
                    {testing && <Loader2 className="size-4 animate-spin" />}
                    {testing ? 'Vérification…' : 'Vérifier'}
                  </Button>
                </div>
                {testLine}
              </div>
            )}

            {provider === 'demo' && (
              <div className="flex items-start gap-3.5">
                <span className="flex size-9 shrink-0 items-center justify-center rounded-[10px] bg-status-offer-soft text-status-offer">
                  <CheckCircle2 className="size-4.5" />
                </span>
                <div className="flex flex-col gap-1">
                  <h3 className="text-[15px] font-semibold">Rien à régler.</h3>
                  <p className="max-w-[640px] text-[13px] leading-relaxed text-muted-foreground">
                    L'appli rejoue des réponses enregistrées : l'import du PDF d'exemple, le ciblage de l'offre d'exemple, la lettre et les idées de projet
                    marchent. Pour tes propres offres, ajoute une clé dans Réglages quand tu veux.
                  </p>
                </div>
              </div>
            )}
          </div>
        </section>

        <section aria-labelledby="machine" className="flex flex-col gap-3.5">
          <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-2">
            <div className="flex flex-col gap-1">
              <h2 id="machine" className="text-[17px] font-semibold">
                Ta machine
              </h2>
              <p className="text-[13.5px] text-muted-foreground">Vérifiée au lancement. Sans LaTeX, l'appli ne peut pas produire le PDF.</p>
            </div>
            <RecheckButton busy={machine.busy} onClick={() => void machine.refresh()} />
          </div>
          <MachineList machine={machine.machine} failed={machine.failed} />
        </section>

        <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3.5 border-t pt-6">
          <button
            type="button"
            onClick={() => void leave({ ...ai, provider: 'demo' })}
            disabled={leaving}
            className="text-[13.5px] font-medium text-primary underline decoration-primary/35 underline-offset-3 hover:decoration-primary"
          >
            Plus tard : découvrir en mode Démo
          </button>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2.5">
            {!ready && (
              <span className="text-[12.5px] text-muted-foreground">
                {relayDown
                  ? 'Choisis ta propre clé Gemini en attendant.'
                  : provider === 'relais'
                    ? "Ajoute d'abord ton code d'accès."
                    : keyed(provider)
                      ? `Ajoute d'abord ta clé ${KEY_NAMES[provider]}.`
                      : "Vérifie d'abord qu'Ollama répond."}
              </span>
            )}
            {ready && latexMissing && (
              <span className="max-w-[380px] text-right text-[12.5px] text-muted-foreground">
                LaTeX peut attendre : l'import et la bibliothèque marchent sans lui, seul le PDF attendra.
              </span>
            )}
            <Button onClick={() => void leave(ai)} disabled={!ready || leaving} className="h-11 gap-2 px-5 text-[14px] font-semibold">
              {leaving && <Loader2 className="size-4 animate-spin" />}
              Continuer vers mon CV de base
              <ArrowRight className="size-4" />
            </Button>
          </div>
        </div>
      </div>
    </>
  )
}
