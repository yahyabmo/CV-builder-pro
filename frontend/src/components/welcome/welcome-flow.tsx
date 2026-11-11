import { Check, ChevronLeft, Info, Lock, PencilLine, PlayCircle, Upload } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { useMe } from '@/hooks/use-me'
import type { Route } from '@/hooks/use-route'
import { api } from '@/lib/api'
import { LAST_OPENED } from '@/lib/bases'
import type { SettingsInfo } from '@/lib/types'
import { cn } from '@/lib/utils'
import { clearIntent, readIntent, type WelcomeIntent } from '@/lib/welcome-intent'

import { AddStep } from './add-step'

import { ImportStep } from './import-step'
import { ManualStep } from './manual-step'
import { ReviewStep } from './review-step'
import { SetupStep } from './setup-step'

type WelcomeRoute = Extract<Route, { view: 'welcome' }>

interface WelcomeFlowProps {
  route: WelcomeRoute
  navigate: (route: Route) => void
  refresh: () => Promise<void>
}

/** Le premier lancement, en plein écran : régler l'IA, puis importer son CV, le saisir, ou garder l'exemple. */
export function WelcomeFlow({ route, navigate, refresh }: WelcomeFlowProps) {
  const done = {
    onTarget: (slug: string) => navigate({ view: 'target', source: slug }),
    onStyle: (slug: string) => navigate({ view: 'cv', slug }),
    refresh,
  }
  // Sortie de l'ajout ou du remplacement d'un CV classique : retour au dernier CV ouvert.
  const leave = () => {
    clearIntent()
    let last = 'base'
    try {
      last = localStorage.getItem(LAST_OPENED) ?? 'base'
    } catch {
      /* stockage indisponible */
    }
    navigate({ view: 'cv', slug: last })
  }
  const intent = readIntent()
  return (
    <div className="h-dvh overflow-y-auto bg-background">
      {route.step === 'setup' && <SetupStep navigate={navigate} />}
      {(route.step === 'new' || (route.step === 'home' && intent?.mode === 'new')) && <AddStep navigate={navigate} refresh={refresh} leave={leave} />}
      {route.step === 'home' && intent?.mode !== 'new' && <Home navigate={navigate} refresh={refresh} intent={intent} leave={leave} />}
      {route.step === 'import' && <ImportStep navigate={navigate} />}
      {route.step === 'review' && <ReviewStep key={route.id} id={route.id} navigate={navigate} {...done} />}
      {route.step === 'manual' && <ManualStep navigate={navigate} {...done} />}
    </div>
  )
}

const STEPS = ['Importer', 'Relire', 'Valider']

/** L'en-tête des étapes : retour, progression, et une mention à droite. */
export function FlowHeader({ back, current, aside, title }: { back: () => void; current?: number; aside?: React.ReactNode; title?: string }) {
  return (
    <header className="sticky top-0 z-10 flex flex-wrap items-center gap-4 border-b bg-background/95 px-6 py-3.5 backdrop-blur">
      <button type="button" onClick={back} className="flex items-center gap-1 rounded-md px-1.5 py-1 text-[13px] text-foreground/80 hover:bg-muted">
        <ChevronLeft className="size-4" /> Retour
      </button>
      {current !== undefined ? (
        <ol aria-label="Étapes" className="mx-auto flex items-center gap-2.5 text-[12.5px]">
          {STEPS.map((step, i) => (
            <li key={step} className="flex items-center gap-2.5">
              {i > 0 && <span aria-hidden="true" className="h-px w-7 bg-border" />}
              <span className={cn('flex items-center gap-1.5', i === current ? 'font-semibold' : i < current ? 'text-status-offer' : 'text-muted-foreground')} aria-current={i === current ? 'step' : undefined}>
                <span
                  className={cn(
                    'flex size-5.5 items-center justify-center rounded-full text-[11.5px]',
                    i === current ? 'bg-primary text-primary-foreground' : i < current ? 'bg-status-offer-soft' : 'border',
                  )}
                >
                  {i < current ? <Check className="size-3" /> : i + 1}
                </span>
                {step}
              </span>
            </li>
          ))}
        </ol>
      ) : (
        <span className="mx-auto text-[13.5px] font-semibold">{title}</span>
      )}
      <span className="min-w-16 text-right text-[12px] text-muted-foreground">{aside}</span>
    </header>
  )
}

interface HomeProps {
  navigate: (route: Route) => void
  refresh: () => Promise<void>
  // « replace » : un CV classique existant reçoit un nouveau contenu.
  intent: WelcomeIntent | null
  leave: () => void
}

function Home({ navigate, refresh, intent, leave }: HomeProps) {
  const replacing = intent?.mode === 'replace' ? intent : null
  const [settings, setSettings] = useState<SettingsInfo | null>(null)
  const me = useMe()
  useEffect(() => {
    api.getSettings().then(setSettings, () => setSettings(null))
  }, [])
  const provider = settings?.ai.provider
  const missingKey = settings != null && provider != null && provider in settings.keys && !settings.keys[provider]

  const keepExample = async () => {
    try {
      await api.dismissWelcome()
      await refresh()
      navigate({ view: 'cv', slug: 'base' })
    } catch (error) {
      toast.error('Impossible de continuer', { description: error instanceof Error ? error.message : String(error) })
    }
  }

  return (
    <div className="mx-auto flex max-w-[1040px] flex-col gap-9 px-6 pt-14 pb-12">
      <div className="flex items-center gap-2.5">
        <img src="/favicon.png" alt="" className="size-7.5" />
        <span className="text-[15px] font-semibold tracking-tight">CV Builder Pro</span>
        {replacing && (
          <button type="button" onClick={leave} className="ml-auto flex items-center gap-1 rounded-md px-1.5 py-1 text-[13px] text-foreground/80 hover:bg-muted">
            <ChevronLeft className="size-4" /> Retour à mes CV
          </button>
        )}
      </div>

      <div className="flex max-w-[680px] flex-col gap-2.5">
        <h1 className="text-[34px] leading-tight font-semibold tracking-tight text-balance">
          {replacing ? `Remplacer « ${replacing.name} »` : 'Commençons par ton CV de base.'}
        </h1>
        <p className="text-[15.5px] leading-relaxed text-muted-foreground">
          {replacing
            ? "Le nouveau contenu prend sa place ; l'ancien reste récupérable dans la corbeille. Tes autres CV classiques et tes candidatures ne bougent pas."
            : "C'est la version que tu adapteras ensuite à chaque offre. Elle sert aussi à remplir ta bibliothèque : tout ce qui est vrai sur ton parcours, et que l'IA pourra utiliser."}
        </p>
      </div>

      <div className={cn('grid gap-4', replacing ? 'md:grid-cols-2' : 'md:grid-cols-3')}>
        <Choice
          primary
          badge="Recommandé"
          icon={<Upload className="size-5.5" />}
          tint="bg-status-sent-soft text-status-sent"
          title="Importer mon CV en PDF"
          text="L'appli lit ton PDF, range son contenu dans ses rubriques et le met à son format. Tu relis tout avant de valider."
          facts={[provider === 'demo' ? 'Mode démo : avec le PDF d’exemple' : 'Environ 30 secondes · une requête à l’IA', 'Photo reprise si le PDF en contient une']}
          onClick={() => navigate({ view: 'welcome', step: 'import' })}
        />
        <Choice
          icon={<PencilLine className="size-5.5" />}
          tint="bg-status-interview-soft text-status-interview"
          title="Le remplir à la main"
          text="Section par section : coordonnées, formation, expériences, projets, compétences, langues. Sans IA."
          facts={['Environ 15 minutes', 'Tu peux t’arrêter et reprendre plus tard']}
          onClick={() => navigate({ view: 'welcome', step: 'manual' })}
        />
        {!replacing && <Choice
          icon={<PlayCircle className="size-5.5" />}
          tint="bg-status-offer-soft text-status-offer"
          title="Partir de l'exemple"
          text="Le CV fictif de Camille Laurent, pour découvrir l'appli. Tu le remplaceras quand tu veux, depuis « Mes CV classiques »."
          facts={['Immédiat', 'Avec une offre d’exemple, même sans clé d’IA']}
          onClick={() => void keepExample()}
        />}
      </div>

      <div className="flex flex-wrap gap-x-7 gap-y-2.5 text-[13px] text-muted-foreground">
        <span className="flex items-center gap-2">
          <Lock className="size-3.5" />
          {me?.mode === 'serveur' ? (
            'Tes CV restent dans ton espace : les autres utilisateurs ne les voient jamais.'
          ) : (
            <>
              Tes CV restent sur cette machine, dans le dossier <code className="text-[12.5px]">data/</code>.
            </>
          )}
        </span>
        {missingKey && (
          <span className="flex items-center gap-2">
            <Info className="size-3.5" /> L'import demande un modèle d'IA :{' '}
            <button type="button" onClick={() => navigate({ view: 'settings' })} className="font-medium text-primary underline-offset-2 hover:underline">
              choisir dans Réglages
            </button>{' '}
            (Gemini est gratuit).
          </span>
        )}
      </div>
    </div>
  )
}

interface ChoiceProps {
  icon: React.ReactNode
  tint: string
  title: string
  text: string
  facts: string[]
  onClick: () => void
  primary?: boolean
  badge?: string
}

function Choice({ icon, tint, title, text, facts, onClick, primary, badge }: ChoiceProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'relative flex flex-col gap-3.5 rounded-2xl border bg-card surface p-6 text-left transition-all hover:-translate-y-0.5 hover:shadow-lg focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none',
        primary ? 'border-primary/70 shadow-md ring-1 ring-primary/20' : 'hover:border-foreground/20',
      )}
    >
      {badge && <span className="absolute top-4.5 right-4.5 rounded-full bg-status-sent-soft px-2.5 py-0.5 text-[11.5px] font-semibold text-status-sent">{badge}</span>}
      <span className={cn('flex size-11 items-center justify-center rounded-xl', tint)}>{icon}</span>
      <span className="flex flex-col gap-1.5">
        <span className="text-[17px] font-semibold tracking-tight">{title}</span>
        <span className="text-[13.5px] leading-relaxed text-muted-foreground">{text}</span>
      </span>
      <span className="mt-auto flex flex-col gap-1.5 border-t pt-3 text-[12.5px] text-muted-foreground">
        {facts.map((fact) => (
          <span key={fact}>{fact}</span>
        ))}
      </span>
    </button>
  )
}
