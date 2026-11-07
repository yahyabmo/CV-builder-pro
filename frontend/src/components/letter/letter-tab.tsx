import { ArrowDown, ArrowUp, ClipboardCopy, Download, Info, Loader2, Lock, Mail, Plus, RefreshCw, Sparkles, Trash2, TriangleAlert } from 'lucide-react'
import { lazy, Suspense, useCallback, useState } from 'react'
import { toast } from 'sonner'

import { AutoTextarea, Field } from '@/components/editor/fields'
import { Segmented } from '@/components/style/controls'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Textarea } from '@/components/ui/textarea'
import type { LetterEditor } from '@/hooks/use-letter-editor'
import { routeHash } from '@/hooks/use-route'
import { api } from '@/lib/api'
import type { LetterCheck } from '@/lib/types'
import { cn } from '@/lib/utils'

const LatexTab = lazy(() => import('@/components/latex/latex-tab'))

const CHECK_ICON: Record<LetterCheck['kind'], React.ReactNode> = {
  tournure: <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-warning" />,
  profil: <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-warning" />,
  longueur: <Info className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />,
}

/** L'onglet « Lettre » : la lettre de motivation de ce CV ciblé. */
export function LetterTab({ slug, letter: editor }: { slug: string; letter: LetterEditor }) {
  const [view, setView] = useState<'text' | 'latex'>('text')
  const [regenerating, setRegenerating] = useState(false)
  const [leaving, setLeaving] = useState(false)
  const { state, letter } = editor

  const loadSource = useCallback(() => api.letterSource(slug), [slug])
  const saveSource = useCallback((tex: string) => api.saveLetterSource(slug, tex), [slug])

  if (state === null) {
    return (
      <div className="flex justify-center p-10 text-muted-foreground">
        <Loader2 className="size-5 animate-spin" />
      </div>
    )
  }
  if (!state.available) {
    return (
      <Empty
        title="Ce CV ne vise aucune offre"
        text="La lettre s'écrit pour une offre précise : cible d'abord une offre à partir de ce CV."
        action={
          <Button size="sm" className="gap-1.5" onClick={() => (window.location.hash = routeHash({ view: 'target', source: slug }))}>
            <Sparkles className="size-3.5" /> Cibler une offre
          </Button>
        }
      />
    )
  }
  if (letter === null) {
    return (
      <ScrollArea className="h-full">
        <div className="mx-auto max-w-2xl px-5 py-5">
          <GenerateForm editor={editor} />
        </div>
      </ScrollArea>
    )
  }

  const copy = async () => {
    try {
      const { text } = await api.letterText(slug)
      await navigator.clipboard.writeText(text)
      toast.success('Texte de la lettre copié')
    } catch (error) {
      toast.error('Copie impossible', { description: (error as Error).message })
    }
  }

  const backToVisual = async () => {
    try {
      const result = await api.letterToVisual(slug)
      editor.applyCompile(result.compile)
      editor.refresh()
      toast.success('Retour au mode visuel')
    } catch (error) {
      toast.error('Retour impossible', { description: (error as Error).message })
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-b px-4 py-2">
        <Segmented
          value={view}
          onChange={setView}
          options={[
            { value: 'text', label: 'Texte' },
            { value: 'latex', label: 'LaTeX' },
          ]}
        />
        <span className="text-[11.5px] text-muted-foreground tabular-nums">{state.words} mots</span>
        <span className="ml-auto flex items-center gap-1">
          <Button variant="ghost" size="sm" className="h-7 gap-1 px-2 text-[12px]" onClick={() => setRegenerating(true)}>
            <RefreshCw className="size-3.5" /> Regénérer
          </Button>
          <Button variant="ghost" size="sm" className="h-7 gap-1 px-2 text-[12px]" onClick={() => void copy()}>
            <ClipboardCopy className="size-3.5" /> Copier le texte
          </Button>
          <Button size="sm" className="h-7 gap-1 px-2.5 text-[12px]" asChild disabled={!editor.pdfVersion}>
            <a href={api.letterPdfUrl(slug, editor.pdfVersion)} download={`${state.file_stem}.pdf`} aria-label="Télécharger la lettre en PDF">
              <Download className="size-3.5" /> PDF
            </a>
          </Button>
        </span>
      </div>

      {editor.manual && (
        <div role="status" className="flex shrink-0 items-center gap-2 border-b border-warning/30 bg-warning/10 px-4 py-2 text-[12px]">
          <Lock className="size-3.5 shrink-0 text-warning" />
          <span className="min-w-0 flex-1">
            <span className="font-medium">Mode manuel.</span> La lettre suit son code LaTeX : les champs sont verrouillés.
          </span>
          <Button variant="outline" size="sm" className="h-7 shrink-0 bg-background text-[12px]" onClick={() => setLeaving(true)}>
            Revenir au mode visuel
          </Button>
        </div>
      )}

      <div className="min-h-0 flex-1">
        {view === 'latex' ? (
          <Suspense
            fallback={
              <div className="flex h-full items-center justify-center text-muted-foreground">
                <Loader2 className="size-5 animate-spin" />
              </div>
            }
          >
            <LatexTab
              adapter={{
                key: `${slug}:lettre:${editor.pdfVersion}:${editor.manual}`,
                load: loadSource,
                save: saveSource,
                onSaved: (result) => {
                  editor.applyCompile(result.compile)
                  editor.refresh()
                },
                recompile: editor.recompile,
                manual: editor.manual,
                locked: null,
                compile: editor.compile,
                texUrl: api.letterTexUrl(slug),
                fileName: `${state.file_stem}.tex`,
                texts: {
                  generated: 'Généré depuis les champs de la lettre. Le modifier puis compiler passe la lettre en mode manuel.',
                  manual: 'Ce code est la source de la lettre.',
                  confirmTitle: 'Passer la lettre en mode manuel ?',
                  confirmText:
                    'Ton code LaTeX devient la source de la lettre et ses champs seront verrouillés. Tu pourras revenir au mode visuel, mais tes modifications du code seront alors perdues.',
                },
              }}
            />
          </Suspense>
        ) : (
          <ScrollArea className="h-full">
            <fieldset
              disabled={editor.manual}
              className={cn('mx-auto block max-w-2xl min-w-0 px-5 py-5', editor.manual && 'pointer-events-none opacity-55 select-none')}
            >
              <LetterFields editor={editor} />
            </fieldset>
          </ScrollArea>
        )}
      </div>

      <RegenerateDialog editor={editor} open={regenerating} onClose={() => setRegenerating(false)} />

      <AlertDialog open={leaving} onOpenChange={setLeaving}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Revenir au mode visuel ?</AlertDialogTitle>
            <AlertDialogDescription>
              Le code LaTeX de la lettre sera refait à partir de ses champs : tes modifications faites dans le code seront perdues.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Garder le mode manuel</AlertDialogCancel>
            <AlertDialogAction className="bg-destructive text-white hover:bg-destructive/90" onClick={() => void backToVisual()}>
              Revenir au mode visuel
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

function Empty({ title, text, action }: { title: string; text: string; action: React.ReactNode }) {
  return (
    <div className="flex h-full items-center justify-center p-8">
      <div className="flex max-w-xs flex-col items-center gap-3 text-center">
        <div className="flex size-10 items-center justify-center rounded-xl bg-muted text-muted-foreground">
          <Mail className="size-5" />
        </div>
        <p className="text-[13px] font-medium">{title}</p>
        <p className="text-[12px] text-muted-foreground">{text}</p>
        {action}
      </div>
    </div>
  )
}

/** Les deux questions avant d'écrire : c'est ce qui donne une âme à la lettre. */
function Questions({ why, detail, setWhy, setDetail }: { why: string; detail: string; setWhy: (v: string) => void; setDetail: (v: string) => void }) {
  return (
    <div className="flex flex-col gap-4">
      <label className="flex flex-col gap-1.5">
        <span className="text-[12.5px] font-medium">Pourquoi cette offre te parle vraiment</span>
        <span className="text-[11.5px] text-muted-foreground">
          Avec tes mots, même maladroits. Par exemple : « J'ai déjà mis un assistant IA en production seul, et le plus dur, c'est
          de le rendre fiable. Ici, c'est exactement ce sujet, à grande échelle et en équipe. »
        </span>
        <Textarea value={why} onChange={(e) => setWhy(e.target.value)} className="min-h-24 text-[13px]" aria-label="Pourquoi cette offre te parle" />
      </label>
      <label className="flex flex-col gap-1.5">
        <span className="text-[12.5px] font-medium">Un détail sur l'entreprise ou l'équipe qui t'a marqué</span>
        <span className="text-[11.5px] text-muted-foreground">
          Ce que tu as vu ou entendu. Par exemple : « Au salon de l'emploi, la responsable de l'équipe a dit que la plupart des agents
          IA restent au stade du prototype. »
        </span>
        <Textarea value={detail} onChange={(e) => setDetail(e.target.value)} className="min-h-20 text-[13px]" aria-label="Un détail qui t'a marqué" />
      </label>
      <p className="text-[11.5px] text-muted-foreground">
        Facultatif, mais c'est ce qui rend la lettre personnelle : sans tes réponses, elle s'appuie seulement sur ton CV et l'offre.
      </p>
    </div>
  )
}

function GenerateForm({ editor }: { editor: LetterEditor }) {
  const [why, setWhy] = useState('')
  const [detail, setDetail] = useState('')
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-1">
        <h2 className="text-[15px] font-semibold tracking-tight">Ta lettre de motivation</h2>
        <p className="text-[12.5px] text-muted-foreground">
          Écrite pour l'offre de ce CV, à partir de ton CV, de ta bibliothèque et de tes règles (Réglages → Lettre de
          motivation). Tu la relis et la retouches ensuite, comme le CV.
        </p>
      </div>
      <Questions why={why} detail={detail} setWhy={setWhy} setDetail={setDetail} />
      <div className="flex items-center gap-2">
        <Button className="gap-1.5" disabled={editor.generating} onClick={() => void editor.generate(why, detail)}>
          {editor.generating ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
          {editor.generating ? 'Écriture en cours…' : 'Générer ma lettre'}
        </Button>
        <span className="text-[11.5px] text-muted-foreground">1 requête, 30 s à 2 min</span>
      </div>
    </div>
  )
}

function RegenerateDialog({ editor, open, onClose }: { editor: LetterEditor; open: boolean; onClose: () => void }) {
  const [why, setWhy] = useState('')
  const [detail, setDetail] = useState('')
  const [opened, setOpened] = useState(false)
  if (open !== opened) {
    setOpened(open)
    if (open && editor.letter) {
      setWhy(editor.letter.why)
      setDetail(editor.letter.detail)
    }
  }
  return (
    <Dialog open={open} onOpenChange={(value) => !value && onClose()}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Regénérer la lettre</DialogTitle>
          <DialogDescription>La nouvelle lettre remplace l'actuelle, retouches comprises (Ctrl+Z ne la ramène pas).</DialogDescription>
        </DialogHeader>
        <Questions why={why} detail={detail} setWhy={setWhy} setDetail={setDetail} />
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            Annuler
          </Button>
          <Button
            className="gap-1.5"
            disabled={editor.generating}
            onClick={async () => {
              if (await editor.generate(why, detail)) onClose()
            }}
          >
            {editor.generating ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />} Regénérer
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

/** Les champs de la lettre, chacun modifiable ; les alertes en tête. */
function LetterFields({ editor }: { editor: LetterEditor }) {
  const letter = editor.letter
  const checks = editor.state?.checks ?? []
  if (!letter) return null
  const set = (mutate: Parameters<LetterEditor['update']>[0], group: string) => editor.update(mutate, group)
  const move = (from: number, to: number) =>
    editor.update((draft) => {
      const [moved] = draft.paragraphs.splice(from, 1)
      draft.paragraphs.splice(to, 0, moved)
    })

  return (
    <div className="flex flex-col gap-5">
      {checks.length > 0 && (
        <ul className="flex flex-col gap-1 rounded-lg border border-warning/30 bg-warning/5 p-3" aria-label="Alertes de la lettre">
          {checks.map((check) => (
            <li key={check.text} className="flex items-start gap-1.5 text-[12px]">
              {CHECK_ICON[check.kind]}
              {check.text}
            </li>
          ))}
        </ul>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <Field
          label="Destinataire (une ligne par élément)"
          multiline
          value={letter.recipient.join('\n')}
          onChange={(v) => set((d) => void (d.recipient = v.split('\n')), 'recipient')}
        />
        <Field label="Lieu et date" value={letter.place_date} onChange={(v) => set((d) => void (d.place_date = v), 'place_date')} />
      </div>
      <Field label="Objet" value={letter.subject} onChange={(v) => set((d) => void (d.subject = v), 'subject')} />
      <Field label="Formule d'appel" value={letter.salutation} onChange={(v) => set((d) => void (d.salutation = v), 'salutation')} />

      <div className="flex flex-col gap-2">
        <span className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">Paragraphes</span>
        {letter.paragraphs.map((paragraph, i) => (
          <div key={i} className="group/p flex items-start gap-1.5">
            <span className="mt-2 w-4 shrink-0 text-right text-[11px] text-muted-foreground tabular-nums">{i + 1}</span>
            <AutoTextarea
              value={paragraph}
              onChange={(e) => set((d) => void (d.paragraphs[i] = e.target.value), `paragraph-${i}`)}
              aria-label={`Paragraphe ${i + 1}`}
            />
            <span className="flex shrink-0 flex-col opacity-60 group-hover/p:opacity-100">
              <Button variant="ghost" size="icon" className="size-6" aria-label={`Monter le paragraphe ${i + 1}`} disabled={i === 0} onClick={() => move(i, i - 1)}>
                <ArrowUp className="size-3" />
              </Button>
              <Button variant="ghost" size="icon" className="size-6" aria-label={`Descendre le paragraphe ${i + 1}`} disabled={i === letter.paragraphs.length - 1} onClick={() => move(i, i + 1)}>
                <ArrowDown className="size-3" />
              </Button>
              <Button variant="ghost" size="icon" className="size-6 hover:text-destructive" aria-label={`Supprimer le paragraphe ${i + 1}`} onClick={() => editor.update((d) => void d.paragraphs.splice(i, 1))}>
                <Trash2 className="size-3" />
              </Button>
            </span>
          </div>
        ))}
        <Button variant="ghost" size="sm" className="h-7 self-start px-2 text-[12px] text-muted-foreground" onClick={() => editor.update((d) => void d.paragraphs.push(''))}>
          <Plus className="size-3.5" /> Paragraphe
        </Button>
      </div>

      <Field label="Formule de fin" multiline value={letter.closing} onChange={(v) => set((d) => void (d.closing = v), 'closing')} />
      <Field label="Signature" value={letter.signature} onChange={(v) => set((d) => void (d.signature = v), 'signature')} />
    </div>
  )
}
