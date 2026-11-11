import { ChevronLeft, Copy, Loader2, PencilLine, Upload } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import type { Route } from '@/hooks/use-route'
import { api } from '@/lib/api'
import { baseCVs } from '@/lib/bases'
import type { CVSummary } from '@/lib/types'
import { cn } from '@/lib/utils'
import { clearIntent, setIntent } from '@/lib/welcome-intent'

type Way = 'import' | 'manual' | 'copy'

/** « + Ajouter » : un CV classique de plus, sans toucher aux autres ni aux candidatures. */
export function AddStep({ navigate, refresh, leave }: { navigate: (route: Route) => void; refresh: () => Promise<void>; leave: () => void }) {
  const [name, setName] = useState('')
  const [way, setWay] = useState<Way>('import')
  const [bases, setBases] = useState<CVSummary[]>([])
  const [source, setSource] = useState('base')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.listCVs().then((all) => setBases(baseCVs(all)), () => undefined)
  }, [])

  const go = async () => {
    const clean = name.trim()
    if (!clean) {
      toast.error('Donne-lui un nom', { description: 'Par exemple « CV Data » ou « English CV ».' })
      return
    }
    if (way !== 'copy') {
      setIntent({ mode: 'new', name: clean })
      navigate({ view: 'welcome', step: way })
      return
    }
    setBusy(true)
    try {
      const created = await api.createCV(clean, source, 'base')
      clearIntent()
      await refresh()
      toast.success(`« ${clean} » ajouté à tes CV classiques`)
      navigate({ view: 'cv', slug: created.slug })
    } catch (error) {
      toast.error('Copie impossible', { description: (error as Error).message })
      setBusy(false)
    }
  }

  const ways: { id: Way; icon: React.ReactNode; title: string; text: string }[] = [
    { id: 'import', icon: <Upload className="size-5" />, title: 'Importer un CV en PDF', text: "L'appli lit ton PDF et le range dans ses rubriques. Tu relis tout avant de valider." },
    { id: 'manual', icon: <PencilLine className="size-5" />, title: 'Le remplir à la main', text: "Les mêmes étapes qu'au premier lancement, rubrique par rubrique." },
    { id: 'copy', icon: <Copy className="size-5" />, title: 'Copier un de mes CV classiques', text: 'Une copie à modifier ensuite.' },
  ]

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-10 flex items-center border-b bg-background/95 px-6 py-3.5 backdrop-blur">
        <button type="button" onClick={leave} className="flex items-center gap-1 rounded-md px-1.5 py-1 text-[13px] text-foreground/80 hover:bg-muted">
          <ChevronLeft className="size-4" /> Retour à mes CV
        </button>
      </header>
      <main className="mx-auto flex w-full max-w-[880px] flex-col gap-7 px-6 pt-12 pb-12">
        <div className="flex flex-col gap-2">
          <span className="text-[12px] font-semibold tracking-wide text-primary uppercase">Mes CV classiques</span>
          <h1 className="text-[32px] leading-tight font-semibold tracking-tight">Un nouveau CV classique</h1>
          <p className="text-[15px] text-muted-foreground">Tes autres CV classiques et tes candidatures ne bougent pas : celui-ci s'ajoute à la liste.</p>
        </div>
        <label className="flex max-w-sm flex-col gap-1.5">
          <span className="text-[13px] font-medium">Son nom</span>
          <Input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="CV Chef de projet" className="h-10" maxLength={120} />
        </label>
        <div role="radiogroup" aria-label="D'où vient ce CV" className="grid gap-3.5 md:grid-cols-3">
          {ways.map((w) => (
            <button
              key={w.id}
              type="button"
              role="radio"
              aria-checked={way === w.id}
              onClick={() => setWay(w.id)}
              className={cn(
                'surface flex flex-col gap-2.5 rounded-2xl border bg-card p-5 text-left transition-all hover:border-foreground/20 focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none',
                way === w.id && 'border-primary ring-1 ring-primary',
              )}
            >
              <span className="flex size-10 items-center justify-center rounded-xl bg-accent text-primary">{w.icon}</span>
              <span className="text-[15px] font-semibold tracking-tight">{w.title}</span>
              <span className="text-[13px] leading-relaxed text-muted-foreground">{w.text}</span>
              {w.id === 'copy' && bases.length > 0 && (
                <select
                  aria-label="CV classique à copier"
                  value={source}
                  onClick={(e) => e.stopPropagation()}
                  onChange={(e) => {
                    setSource(e.target.value)
                    setWay('copy')
                  }}
                  className="mt-1 h-9 rounded-lg border bg-background px-2 text-[13px]"
                >
                  {bases.map((cv) => (
                    <option key={cv.slug} value={cv.slug}>
                      {cv.meta.name}
                    </option>
                  ))}
                </select>
              )}
            </button>
          ))}
        </div>
        <div className="flex gap-2">
          <Button onClick={() => void go()} disabled={busy} className="h-10 gap-1.5 px-5">
            {busy && <Loader2 className="size-4 animate-spin" />} Continuer
          </Button>
          <Button variant="ghost" className="h-10" onClick={leave}>
            Annuler
          </Button>
        </div>
      </main>
    </div>
  )
}
