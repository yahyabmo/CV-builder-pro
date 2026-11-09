import { CheckCircle2, ChevronDown, CircleAlert, Download, Loader2, Lock, PlugZap, Save } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { KeyForm } from '@/components/setup/key-form'
import { MachineList, RecheckButton } from '@/components/setup/machine-checks'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { Slider } from '@/components/ui/slider'
import { useMachine } from '@/hooks/use-machine'
import { useMe } from '@/hooks/use-me'
import { api } from '@/lib/api'
import { keyed } from '@/lib/keys'
import type { AISettings, ConnectionTest, KeyProvider, OnlineAI, Provider, SettingsInfo } from '@/lib/types'
import { cn } from '@/lib/utils'

import { RulesEditor } from './rules-editor'

const PROVIDERS: { id: Provider; name: string; text: string; other?: boolean }[] = [
  {
    id: 'relais',
    name: 'Gemini de Yahya',
    text: 'Gratuit pour toi, sur invitation : le code d’accès que Yahya t’a donné. Jusqu’à 20 demandes par jour (environ 6 CV ciblés).',
  },
  {
    id: 'gemini',
    name: 'Gemini (ta clé)',
    text: 'Gratuit : 20 requêtes par jour et par modèle (un ciblage en fait 3 ou 4). Les modèles de secours prennent le relais.',
  },
  { id: 'mistral', name: 'Mistral (ta clé)', text: 'Payant : environ 0,02 $ par offre avec Mistral Large.' },
  { id: 'ollama', name: 'Ollama (local)', text: 'Local et gratuit, mais lent sans carte graphique : plusieurs minutes par offre.', other: true },
  {
    id: 'demo',
    name: 'Démo',
    text: "Sans clé, pour essayer l'appli : des réponses enregistrées pour l'offre d'exemple. Tes propres offres demandent un vrai modèle.",
    other: true,
  },
]

const time = (iso: string) => new Date(iso).toLocaleTimeString('fr', { hour: '2-digit', minute: '2-digit' })

export function SettingsPage() {
  const me = useMe()
  if (!me) {
    return (
      <Page>
        <Skeleton className="h-40 w-full rounded-xl" />
      </Page>
    )
  }
  return me.mode === 'serveur' ? <OnlineSettings /> : <LocalSettings />
}

/** En ligne : rien à installer ni à régler pour l'IA. Restent les règles de la lettre. */
function OnlineSettings() {
  const [online, setOnline] = useState<OnlineAI | null | undefined>(undefined)
  useEffect(() => {
    api.getSettings().then(
      (info) => setOnline(info.online ?? null),
      () => setOnline(null),
    )
  }, [])

  const used = online?.ok && online.quota ? online.quota - (online.left ?? 0) : null
  return (
    <Page>
      <p className="text-[13px] text-muted-foreground">En ligne, il n'y a rien à installer ni de clé à coller.</p>

      <section className="flex flex-col gap-3 rounded-xl border bg-card surface p-4">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-[14px] font-semibold">Intelligence artificielle</h2>
          {online !== undefined && (
            <span
              className={cn(
                'rounded-full px-2.5 py-0.5 text-[11.5px] font-semibold',
                online?.ok ? 'bg-success/15 text-success' : 'bg-warning/15 text-warning',
              )}
            >
              {online?.ok ? 'Active' : 'Indisponible'}
            </span>
          )}
        </div>
        <p className="text-[13px] text-muted-foreground">Fournie par Yahya (Gemini). Aucune clé à gérer de ton côté.</p>
        {online === undefined && <Skeleton className="h-8 w-full" />}
        {online && !online.ok && <p className="text-[12.5px] text-warning">{online.message || 'Réessaie dans un moment.'}</p>}
        {online?.exhausted && (
          <p className="text-[12.5px] text-warning">Le crédit offert ce mois-ci est épuisé. Il revient le 1er du mois.</p>
        )}
        {online?.ok && online.quota != null && used != null && (
          <div className="flex flex-col gap-1.5">
            <div className="flex justify-between text-[13px]">
              <span>Aujourd'hui</span>
              <span className="font-semibold tabular-nums">
                {used} / {online.quota} demandes
              </span>
            </div>
            <div
              role="progressbar"
              aria-label="Demandes utilisées aujourd'hui"
              aria-valuemin={0}
              aria-valuemax={online.quota}
              aria-valuenow={used}
              className="h-2 overflow-hidden rounded-full bg-muted"
            >
              <div className="h-full bg-primary" style={{ width: `${Math.min(100, (used / online.quota) * 100)}%` }} />
            </div>
            <p className="text-[12px] text-muted-foreground">
              Le compteur repart à zéro à minuit (heure de Paris). Un CV ciblé en utilise 3, une lettre 1.
            </p>
          </div>
        )}
      </section>

      <section className="flex flex-col gap-2 rounded-xl border bg-card surface p-4">
        <h2 className="text-[14px] font-semibold">Tes données</h2>
        <p className="text-[13px] text-muted-foreground">Télécharge tout dans un zip : CV, lettres, bibliothèque, thèmes et règles.</p>
        <div className="flex flex-wrap items-center gap-3">
          <Button asChild variant="outline" size="sm" className="gap-1.5">
            <a href={api.exportUrl} download>
              <Download className="size-3.5" /> Tout télécharger
            </a>
          </Button>
          <a href="#/privacy" className="text-[12.5px] font-medium text-primary underline-offset-2 hover:underline">
            Confidentialité et suppression du compte
          </a>
        </div>
      </section>

      <section className="flex flex-col gap-2 rounded-xl border bg-card surface p-4">
        <h2 className="text-[14px] font-semibold">Compilation des CV</h2>
        <p className="flex items-center gap-1.5 text-[13px] text-muted-foreground">
          <CheckCircle2 className="size-4 shrink-0 text-success" />
          Le PDF est fabriqué sur le serveur : rien à installer sur ton ordinateur.
        </p>
      </section>

      <RulesEditor
        kind="lettre"
        title="Lettre de motivation : tes règles"
        description="Données à l'IA à chaque lettre (onglet Lettre d'un CV ciblé)."
      />

      <RulesEditor
        kind="tournures"
        title="Lettre de motivation : tournures à bannir"
        description="Interdites à l'IA, et signalées dans la lettre si elles y apparaissent (même après tes retouches)."
        addLabel="Ajouter une tournure"
        placeholder="ex. je me permets"
      />
    </Page>
  )
}

function LocalSettings() {
  const [info, setInfo] = useState<SettingsInfo | null>(null)
  const [form, setForm] = useState<AISettings | null>(null)
  const [fallbacks, setFallbacks] = useState('')
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [test, setTest] = useState<ConnectionTest | null>(null)
  const [others, setOthers] = useState(false)

  const load = (next: SettingsInfo) => {
    setInfo(next)
    setForm(next.ai)
    setFallbacks(next.ai.gemini_fallbacks.join(', '))
  }

  useEffect(() => {
    api.getSettings().then(load, (error: Error) => toast.error('Réglages indisponibles', { description: error.message }))
  }, [])

  if (!info || !form) {
    return (
      <Page>
        <Skeleton className="h-40 w-full rounded-xl" />
        <Skeleton className="h-28 w-full rounded-xl" />
      </Page>
    )
  }

  const edited: AISettings = {
    ...form,
    gemini_fallbacks: fallbacks
      .split(',')
      .map((m) => m.trim())
      .filter(Boolean),
  }
  const dirty = JSON.stringify(edited) !== JSON.stringify(info.ai)
  const set = (patch: Partial<AISettings>) => setForm({ ...form, ...patch })

  const save = async () => {
    setSaving(true)
    try {
      load(await api.saveSettings(edited))
      setTest(null)
      toast.success('Réglages enregistrés')
    } catch (error) {
      toast.error('Enregistrement impossible', { description: (error as Error).message })
    } finally {
      setSaving(false)
    }
  }

  const runTest = async () => {
    setTesting(true)
    setTest(null)
    try {
      setTest(await api.testConnection())
      setInfo(await api.getSettings())
    } catch (error) {
      setTest({ ok: false, model: '', seconds: 0, message: (error as Error).message })
    } finally {
      setTesting(false)
    }
  }

  const blocked = Object.entries(info.blocked)
  // Ollama et Démo restent possibles, rangés sous « Autres options » (ouvertes si l'un est choisi).
  const showOthers = others || PROVIDERS.some((p) => p.other && p.id === form.provider)
  const card = (p: (typeof PROVIDERS)[number]) => (
    <div
      key={p.id}
      className={cn(
        'flex flex-col gap-3 rounded-lg border bg-card surface p-3 transition-colors',
        form.provider === p.id ? 'border-primary/60 ring-1 ring-primary/20' : 'hover:bg-muted/40',
      )}
    >
      <label className="flex cursor-pointer items-start gap-3">
        <RadioGroupItem value={p.id} className="mt-0.5" />
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="text-[13px] font-medium">{p.name}</span>
          <span className="text-[12px] text-muted-foreground">
            {p.text}
            {p.id === 'relais' && !info.relay_ready && ' Pas encore en service.'}
          </span>
        </span>
      </label>
      {keyed(p.id) && (p.id !== 'relais' || info.relay_ready) && <KeyRow provider={p.id} present={info.keys[p.id]} onChange={setInfo} />}
    </div>
  )

  return (
    <Page>
      <section className="flex flex-col gap-3">
        <h2 className="text-[13px] font-semibold">Fournisseur du modèle</h2>
        <RadioGroup value={form.provider} onValueChange={(provider) => set({ provider: provider as Provider })} className="gap-2">
          {PROVIDERS.filter((p) => !p.other).map(card)}
          <button
            type="button"
            onClick={() => setOthers(!showOthers)}
            aria-expanded={showOthers}
            className="flex items-center gap-1.5 self-start py-1 text-[12.5px] font-medium text-muted-foreground hover:text-foreground"
          >
            <ChevronDown className={cn('size-3.5 transition-transform', showOthers && 'rotate-180')} />
            Autres options : Ollama (local), Démo
          </button>
          {showOthers && PROVIDERS.filter((p) => p.other).map(card)}
        </RadioGroup>
        <p className="flex items-center gap-2 text-[12px] text-muted-foreground">
          <Lock className="size-3.5 shrink-0" />
          Les clés et le code d'accès vont dans le fichier .env de ce dossier, lisible par toi seul. Ils ne sont jamais renvoyés ni affichés.
        </p>
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="text-[13px] font-semibold">Modèles</h2>
        {form.provider === 'gemini' && (
          <>
            <Field label="Modèle principal">
              <Input value={form.gemini_model} onChange={(e) => set({ gemini_model: e.target.value })} className="h-8 font-mono text-[12.5px]" />
            </Field>
            <Field label="Modèles de secours, dans l'ordre" hint="Pris quand le précédent est surchargé ou a épuisé son quota du jour.">
              <Input value={fallbacks} onChange={(e) => setFallbacks(e.target.value)} className="h-8 font-mono text-[12.5px]" />
            </Field>
          </>
        )}
        {form.provider === 'relais' && (
          <p className="text-[12.5px] text-muted-foreground">
            Le relais de Yahya choisit le modèle : <code className="font-mono">{form.relais_model}</code>, le plus économe.
          </p>
        )}
        {form.provider === 'mistral' && (
          <Field label="Modèle">
            <Input value={form.mistral_model} onChange={(e) => set({ mistral_model: e.target.value })} className="h-8 font-mono text-[12.5px]" />
          </Field>
        )}
        {form.provider === 'ollama' && (
          <>
            <Field label="Modèle" hint="Téléchargé avec « ollama pull <modèle> ».">
              <Input value={form.ollama_model} onChange={(e) => set({ ollama_model: e.target.value })} className="h-8 font-mono text-[12.5px]" />
            </Field>
            <Field label="Adresse d'Ollama">
              <Input value={form.ollama_url} onChange={(e) => set({ ollama_url: e.target.value })} className="h-8 font-mono text-[12.5px]" />
            </Field>
          </>
        )}
        <Field label={`Température : ${form.temperature.toFixed(2).replace('.', ',')}`} hint="Basse : réponses régulières et prudentes. Haute : plus variées.">
          <Slider
            value={[form.temperature]}
            min={0}
            max={1}
            step={0.05}
            onValueChange={([value]) => set({ temperature: value })}
            className="max-w-xs"
            aria-label="Température"
          />
        </Field>
      </section>

      <div className="flex flex-wrap items-center gap-2 border-t pt-5">
        <Button onClick={() => void save()} disabled={!dirty || saving} className="gap-1.5">
          {saving ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />} Enregistrer
        </Button>
        <Button variant="outline" onClick={() => void runTest()} disabled={dirty || testing} className="gap-1.5">
          {testing ? <Loader2 className="size-4 animate-spin" /> : <PlugZap className="size-4" />} Tester la connexion
        </Button>
        {dirty && <span className="text-[12px] text-muted-foreground">Enregistre avant de tester.</span>}
        {test && (
          <span role="status" className={cn('flex items-center gap-1.5 text-[12.5px]', test.ok ? 'text-success' : 'text-destructive')}>
            {test.ok ? <CheckCircle2 className="size-4" /> : <CircleAlert className="size-4" />}
            {test.ok ? `${test.model} répond (${String(test.seconds).replace('.', ',')} s)` : test.message}
          </span>
        )}
      </div>

      <MachineSection />

      <section className="flex flex-col gap-2">
        <h2 className="text-[13px] font-semibold">Consommation</h2>
        <dl className="grid grid-cols-3 gap-2">
          <Stat label="Appels ce mois-ci" value={info.usage.calls.toLocaleString('fr')} />
          <Stat label="Jetons" value={(info.usage.input + info.usage.output).toLocaleString('fr')} />
          <Stat
            label="Coût estimé"
            value={info.usage.cost == null ? 'inconnu' : info.usage.cost === 0 ? 'gratuit' : `${info.usage.cost.toFixed(2).replace('.', ',')} $`}
          />
        </dl>
        {blocked.length > 0 && (
          <ul className="flex flex-col gap-1 text-[12px]">
            {blocked.map(([model, until]) => (
              <li key={model} className="flex items-center gap-1.5 text-warning">
                <CircleAlert className="size-3.5" />
                <span className="text-foreground">
                  <code className="font-mono">{model}</code> : quota du jour épuisé, de retour vers {time(until)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <RulesEditor
        kind="lettre"
        title="Lettre de motivation : tes règles"
        description="Données à l'IA à chaque lettre (onglet Lettre d'un CV ciblé)."
      />

      <RulesEditor
        kind="tournures"
        title="Lettre de motivation : tournures à bannir"
        description="Interdites à l'IA, et signalées dans la lettre si elles y apparaissent (même après tes retouches)."
        addLabel="Ajouter une tournure"
        placeholder="ex. je me permets"
      />

      <section className="flex flex-col gap-1.5">
        <h2 className="text-[13px] font-semibold">Consignes de l'IA</h2>
        <p className="text-[12px] text-muted-foreground">
          Elles sont dans le dossier <code className="font-mono">prompts/</code> du projet (analyse.md, plan.md, reecriture.md,
          traduction.md). Tu peux les modifier : elles sont relues à chaque ciblage.
        </p>
      </section>
    </Page>
  )
}

function Page({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full flex-col">
      <header className="flex h-11 shrink-0 items-center border-b px-5">
        <h1 className="text-[13px] font-semibold tracking-tight">Réglages</h1>
      </header>
      <ScrollArea className="min-h-0 flex-1">
        <div className="mx-auto flex max-w-2xl flex-col gap-7 px-6 py-7">{children}</div>
      </ScrollArea>
    </div>
  )
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label className="text-[12px] text-muted-foreground">{label}</Label>
      {children}
      {hint && <p className="text-[11.5px] text-muted-foreground/80">{hint}</p>}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border bg-card surface px-3 py-2">
      <dt className="text-[11px] text-muted-foreground">{label}</dt>
      <dd className="text-[15px] font-semibold tabular-nums">{value}</dd>
    </div>
  )
}

/** La clé d'un fournisseur : enregistrée (remplacer, supprimer) ou à ajouter. */
function KeyRow({ provider, present, onChange }: { provider: KeyProvider; present: boolean; onChange: (info: SettingsInfo) => void }) {
  const [open, setOpen] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)

  const remove = async () => {
    setBusy(true)
    try {
      onChange(await api.deleteKey(provider))
      toast.success(provider === 'relais' ? 'Code supprimé de .env' : 'Clé supprimée de .env')
    } catch (error) {
      toast.error('Suppression impossible', { description: (error as Error).message })
    } finally {
      setBusy(false)
      setConfirming(false)
    }
  }

  if (present && !open) {
    return (
      <div className="flex flex-wrap items-center gap-2 pl-7">
        <span className="flex items-center gap-1.5 text-[12px] font-medium text-success">
          <CheckCircle2 className="size-3.5" /> {provider === 'relais' ? 'Code enregistré' : 'Clé enregistrée'}
        </span>
        <span className="flex-1" />
        <Button variant="outline" size="sm" className="h-7 text-[12px]" onClick={() => setOpen(true)}>
          Remplacer
        </Button>
        {confirming ? (
          <>
            <Button variant="destructive" size="sm" className="h-7 text-[12px]" disabled={busy} onClick={() => void remove()}>
              {provider === 'relais' ? 'Supprimer le code' : 'Supprimer la clé'}
            </Button>
            <Button variant="ghost" size="sm" className="h-7 text-[12px]" onClick={() => setConfirming(false)}>
              Garder
            </Button>
          </>
        ) : (
          <Button variant="outline" size="sm" className="h-7 text-[12px] text-destructive" onClick={() => setConfirming(true)}>
            Supprimer
          </Button>
        )}
      </div>
    )
  }
  return (
    <div className="flex flex-col gap-1.5 pl-7">
      <KeyForm
        compact
        provider={provider}
        onSaved={() => {
          setOpen(false)
          void api.getSettings().then(onChange)
        }}
      />
      {present && (
        <button type="button" onClick={() => setOpen(false)} className="self-start text-[12px] text-muted-foreground hover:text-foreground">
          {provider === 'relais' ? 'Garder le code actuel' : 'Garder la clé actuelle'}
        </button>
      )}
    </div>
  )
}

/** LaTeX, ses paquets et les outils PDF : une ligne si tout est là, le détail sinon. */
function MachineSection() {
  const { machine, busy, failed, refresh } = useMachine()
  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-[13px] font-semibold">Ta machine</h2>
      {machine?.ok ? (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border bg-card surface px-4 py-3">
          <CheckCircle2 className="size-4 text-success" />
          <span className="flex-[1_1_240px] text-[13px]">LaTeX, paquets du CV et outils PDF installés.</span>
          <RecheckButton busy={busy} onClick={() => void refresh()} />
        </div>
      ) : (
        <>
          <MachineList machine={machine} failed={failed} />
          {machine && (
            <div>
              <RecheckButton busy={busy} onClick={() => void refresh()} />
            </div>
          )}
        </>
      )}
    </section>
  )
}
