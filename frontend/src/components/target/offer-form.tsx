import { FileUp, FlaskConical, Link2, Settings, Sparkles, TextCursorInput } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { api } from '@/lib/api'
import { baseCVs } from '@/lib/bases'
import type { CVSummary, SettingsInfo, TargetRequest } from '@/lib/types'

const MIN_TEXT = 80
const PROVIDER_NAME: Record<string, string> = { gemini: 'Gemini', mistral: 'Mistral', ollama: 'Ollama (local)', demo: 'Démo' }

function modelName(settings: SettingsInfo): string {
  const { ai } = settings
  if (ai.provider === 'gemini') return ai.gemini_model
  if (ai.provider === 'mistral') return ai.mistral_model
  if (ai.provider === 'ollama') return ai.ollama_model
  return 'réponses enregistrées'
}

export interface OfferDraft {
  source: string
  mode: 'text' | 'url'
  text: string
  url: string
  projects: string
  language: TargetRequest['language']
}

interface OfferFormProps {
  cvs: CVSummary[] | null
  value: OfferDraft
  onChange: (value: OfferDraft) => void
  onSubmit: (request: TargetRequest) => void
  openSettings: () => void
}

export function OfferForm({ cvs, value, onChange, onSubmit, openSettings }: OfferFormProps) {
  const [settings, setSettings] = useState<SettingsInfo | null>(null)
  const [demoOffer, setDemoOffer] = useState<string | null>(null)
  const file = useRef<HTMLInputElement>(null)
  const set = (patch: Partial<OfferDraft>) => onChange({ ...value, ...patch })

  useEffect(() => {
    api.getSettings().then(setSettings, () => setSettings(null))
  }, [])

  const provider = settings?.ai.provider
  const demo = provider === 'demo'
  useEffect(() => {
    if (demo) api.demoOffer().then(({ text }) => setDemoOffer(text.trim()), () => setDemoOffer(null))
  }, [demo])

  // Le faux modèle des essais n'a pas de clé : seule une clé attendue et absente bloque.
  const missingKey = settings != null && provider != null && provider in settings.keys && !settings.keys[provider]
  const text = value.text.trim()
  const url = value.url.trim()
  // En démo, seule l'offre d'exemple a des réponses enregistrées.
  const otherOffer = demo && (value.mode !== 'text' || text !== demoOffer)
  const ready = (value.mode === 'text' ? text.length >= MIN_TEXT : /^https?:\/\/\S+\.\S+/.test(url)) && !otherOffer

  const submit = (event?: React.FormEvent) => {
    event?.preventDefault()
    if (!ready || missingKey) return
    onSubmit({
      source: value.source,
      ...(value.mode === 'text' ? { text } : { url }),
      ...(value.projects !== 'auto' ? { projects_count: Number(value.projects) } : {}),
      language: value.language,
    })
  }

  const readFile = async (picked: File | undefined) => {
    if (!picked) return
    if (picked.size > 200_000) {
      toast.error('Fichier trop gros', { description: 'Une offre tient en quelques Ko de texte.' })
      return
    }
    set({ text: await picked.text(), mode: 'text' })
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-6">
      <div className="flex flex-col gap-1.5">
        <h2 className="text-lg font-semibold tracking-tight text-balance">Adapter un CV à une offre</h2>
        <p className="max-w-prose text-[13px] text-muted-foreground">
          L'IA lit l'offre, choisit tes compétences et tes projets les plus utiles, reformule tes puces dans son vocabulaire,
          sans rien inventer. Tu relis chaque changement avant que le CV soit créé.
        </p>
      </div>

      {demo && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-primary/25 bg-primary/5 p-3" role="note">
          <FlaskConical className="size-4 shrink-0 text-primary" />
          <p className="min-w-0 flex-1 text-[12.5px]">
            <span className="font-medium">Mode démo.</span>{' '}
            <span className="text-muted-foreground">
              L'IA est remplacée par des réponses enregistrées pour une offre d'exemple. Pour tes offres, choisis un modèle dans
              Réglages.
            </span>
          </p>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-7 text-[12px]"
            disabled={demoOffer == null}
            onClick={() => demoOffer && set({ text: demoOffer, mode: 'text' })}
          >
            Charger l'offre d'exemple
          </Button>
        </div>
      )}

      <section className="flex flex-col gap-2">
        <Label className="text-[12px] text-muted-foreground">L'offre</Label>
        <Tabs value={value.mode} onValueChange={(mode) => set({ mode: mode as OfferDraft['mode'] })} className="gap-2">
          <TabsList className="h-8 w-fit">
            <TabsTrigger value="text" className="gap-1.5 px-3 text-[12px]">
              <TextCursorInput className="size-3.5" /> Texte
            </TabsTrigger>
            <TabsTrigger value="url" className="gap-1.5 px-3 text-[12px]">
              <Link2 className="size-3.5" /> Adresse
            </TabsTrigger>
          </TabsList>
          <TabsContent value="text" className="flex flex-col gap-2">
            <Textarea
              value={value.text}
              onChange={(e) => set({ text: e.target.value })}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) submit()
              }}
              placeholder="Colle ici le texte de l'offre : intitulé, missions, profil recherché…"
              className="min-h-56 resize-y text-[13px] leading-relaxed"
              aria-label="Texte de l'offre"
            />
            <div className="flex items-center gap-2 text-[11.5px] text-muted-foreground">
              <Button type="button" variant="outline" size="sm" className="h-7 gap-1.5 text-[12px]" onClick={() => file.current?.click()}>
                <FileUp className="size-3.5" /> Importer un .txt
              </Button>
              <input ref={file} type="file" accept=".txt,text/plain" className="hidden" onChange={(e) => void readFile(e.target.files?.[0])} />
              <span className="ml-auto tabular-nums">
                {text.length < MIN_TEXT && text.length > 0 ? `encore ${MIN_TEXT - text.length} caractères au moins` : `${text.length} caractères`}
              </span>
            </div>
          </TabsContent>
          <TabsContent value="url" className="flex flex-col gap-2">
            <Input
              value={value.url}
              onChange={(e) => set({ url: e.target.value })}
              placeholder="https://www.welcometothejungle.com/fr/companies/…/jobs/…"
              className="text-[13px]"
              aria-label="Adresse de l'offre"
              type="url"
            />
            <p className="text-[11.5px] text-muted-foreground">
              LinkedIn, Indeed et beaucoup de sites d'emploi bloquent les robots : si la page ne se lit pas, colle le texte de
              l'offre dans l'onglet Texte.
            </p>
          </TabsContent>
        </Tabs>
      </section>

      <section className="grid gap-5 sm:grid-cols-3">
        <div className="flex flex-col gap-2">
          <Label className="text-[12px] text-muted-foreground">À partir de</Label>
          <Select value={value.source} onValueChange={(source) => set({ source })}>
            <SelectTrigger className="h-8 w-full text-[13px]" aria-label="CV de départ">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(cvs ? [...baseCVs(cvs), ...cvs.filter((cv) => cv.meta.kind !== 'base')] : [{ slug: 'base', meta: { name: 'Version classique' } } as CVSummary]).map((cv) => (
                <SelectItem key={cv.slug} value={cv.slug} className="text-[13px]">
                  {cv.meta.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-2">
          <Label className="text-[12px] text-muted-foreground">Projets montrés</Label>
          <Select value={value.projects} onValueChange={(projects) => set({ projects })}>
            <SelectTrigger className="h-8 w-full text-[13px]" aria-label="Nombre de projets">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="auto" className="text-[13px]">Autant que le CV de départ</SelectItem>
              {[1, 2, 3, 4, 5, 6].map((n) => (
                <SelectItem key={n} value={String(n)} className="text-[13px]">
                  {n} projet{n > 1 ? 's' : ''}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-2">
          <Label className="text-[12px] text-muted-foreground">Langue du CV</Label>
          <RadioGroup
            value={value.language}
            onValueChange={(language) => set({ language: language as OfferDraft['language'] })}
            className="flex h-8 items-center gap-3"
          >
            {(
              [
                ['auto', 'Celle de l’offre'],
                ['fr', 'FR'],
                ['en', 'EN'],
              ] as const
            ).map(([key, label]) => (
              <label key={key} className="flex items-center gap-1.5 text-[12.5px]">
                <RadioGroupItem value={key} /> {label}
              </label>
            ))}
          </RadioGroup>
        </div>
      </section>

      <div className="flex flex-wrap items-center gap-3 border-t pt-5">
        <Button type="submit" disabled={!ready || missingKey} className="gap-1.5">
          <Sparkles className="size-4" /> Analyser l'offre
        </Button>
        <kbd className="hidden font-mono text-[10.5px] text-muted-foreground sm:inline">Ctrl Entrée</kbd>
        {otherOffer && (text.length > 0 || url.length > 0) && (
          <span className="text-[11.5px] text-muted-foreground">En mode démo, seule l'offre d'exemple a des réponses.</span>
        )}
        <button
          type="button"
          onClick={openSettings}
          className="ml-auto flex items-center gap-1.5 rounded-md px-2 py-1 text-[11.5px] text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <Settings className="size-3.5" />
          {settings ? (
            missingKey ? (
              <span className="text-destructive">Clé {PROVIDER_NAME[settings.ai.provider] ?? settings.ai.provider} absente : voir Réglages</span>
            ) : (
              <span>
                {PROVIDER_NAME[settings.ai.provider] ?? settings.ai.provider} · {modelName(settings)}
              </span>
            )
          ) : (
            'Réglages'
          )}
        </button>
      </div>
    </form>
  )
}
