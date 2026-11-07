import { Check, CheckCircle2, ChevronDown, ChevronRight, CircleAlert, Download, FileCode2, FileText, Loader2, Lock, Redo2, Undo2 } from 'lucide-react'
import { lazy, Suspense, useCallback, useEffect, useState } from 'react'
import { toast } from 'sonner'

import { AtsTab } from '@/components/ats/ats-tab'
import { ContentEditor } from '@/components/editor/content-editor'
import { ScoreBand } from '@/components/editor/score-band'
import { StyleEditor } from '@/components/style/style-editor'
import { PdfPreview } from '@/components/preview/pdf-preview'
import { LetterTab } from '@/components/letter/letter-tab'
import { OfferTab } from '@/components/target/offer-tab'
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '@/components/ui/resizable'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useCvEditor, type CvEditor, type SyncState } from '@/hooks/use-cv-editor'
import { useLetterEditor } from '@/hooks/use-letter-editor'
import { routeHash } from '@/hooks/use-route'
import { useShortcuts } from '@/hooks/use-shortcuts'
import { api } from '@/lib/api'
import { STATUS, STATUS_ORDER } from '@/lib/applications'
import { applyCut } from '@/lib/cuts'
import type { FocusRequest } from '@/lib/focus'
import type { ApplicationStatus, Cut, PageBox, PageLocation } from '@/lib/types'
import { TABS, WORKSPACE_EVENT, type Tab, type WorkspaceCommand } from '@/lib/workspace-commands'
import { cn } from '@/lib/utils'

// Monaco ne se charge qu'à l'ouverture de l'onglet.
const LatexTab = lazy(() => import('@/components/latex/latex-tab'))

/** L'éditeur et l'aperçu d'un CV. Remonté à chaque changement de CV (clé). */
export function Workspace({ slug }: { slug: string }) {
  const editor = useCvEditor(slug)
  const [tab, setTab] = useState<Tab>('content')
  const [leaving, setLeaving] = useState(false)
  // Aller à un champ (clic sur l'aperçu, mot-clé ajouté) et l'entourer sur la page.
  const [focus, setFocus] = useState<FocusRequest | null>(null)
  const [highlight, setHighlight] = useState<PageBox | null>(null)
  const onLetter = tab === 'letter'
  const letter = useLetterEditor(slug, onLetter, editor.pdfVersion)
  // Sur l'onglet Lettre, annuler, rétablir et enregistrer visent la lettre.
  const doc = onLetter ? letter : editor
  const noop = () => undefined
  useShortcuts({
    undo: doc.manual ? noop : doc.undo,
    redo: doc.manual ? noop : doc.redo,
    save: doc.manual ? doc.recompile : doc.saveNow,
  })

  const { recompile } = editor
  // Stables : l'éditeur de code ne relit le .tex que si le CV a changé.
  const cvSource = useCallback(() => api.getSource(slug), [slug])
  const saveCvSource = useCallback((tex: string) => api.saveSource(slug, tex), [slug])
  useEffect(() => {
    const onCommand = (event: Event) => {
      const command = (event as CustomEvent<WorkspaceCommand>).detail
      if (command.action === 'tab') setTab(command.tab)
      else recompile()
    }
    window.addEventListener(WORKSPACE_EVENT, onCommand)
    return () => window.removeEventListener(WORKSPACE_EVENT, onCommand)
  }, [recompile])

  const revealField = useCallback((location: PageLocation) => {
    setTab('content')
    setFocus({ location, nonce: Date.now() })
  }, [])

  const pick = useCallback(
    async ({ x, y }: { x: number; y: number }) => {
      const found = await api.locate(slug, x, y).catch(() => null)
      if (!found) return
      setHighlight(found.box)
      revealField(found)
    },
    [slug, revealField],
  )

  if (editor.loadError) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-center text-[13px] text-muted-foreground">
        <div className="flex max-w-sm flex-col items-center gap-2">
          <CircleAlert className="size-6 text-destructive" />
          <p className="font-medium text-foreground">Impossible d'ouvrir ce CV</p>
          <p>{editor.loadError}</p>
        </div>
      </div>
    )
  }

  const name = editor.detail?.meta.name ?? ''
  const kind = editor.detail?.meta.kind
  const stem = editor.detail?.file_stem ?? slug
  const url = editor.pdfVersion ? api.pdfUrl(slug, editor.pdfVersion) : null

  const backToVisual = async () => {
    try {
      const result = await api.backToVisual(slug)
      editor.applyCompile(result.compile)
      editor.setMode(result.mode)
      toast.success('Retour au mode visuel')
    } catch (error) {
      toast.error('Retour impossible', { description: (error as Error).message })
    }
  }

  return (
    <ResizablePanelGroup orientation="horizontal" id="workspace">
      <ResizablePanel id="editor" defaultSize="48%" minSize="32%">
        <div className="flex h-full flex-col">
          <header className="@container flex h-12 shrink-0 items-center gap-2 border-b px-4">
            <nav aria-label="Fil d'Ariane" className="flex min-w-0 items-center gap-1.5">
              {kind === 'cv' && (
                <>
                  <a href={routeHash({ view: 'cvs' })} className="shrink-0 text-[13px] text-muted-foreground transition-colors hover:text-foreground">
                    Candidatures
                  </a>
                  <ChevronRight aria-hidden className="size-3.5 shrink-0 text-muted-foreground/60" />
                </>
              )}
              <h1 className="truncate text-[13.5px] font-semibold tracking-tight">
                {name || <Skeleton className="h-4 w-40" />}
              </h1>
            </nav>
            {kind === 'base' && <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">CV de base</span>}
            {editor.detail && kind === 'cv' && <StatusMenu key={slug} slug={slug} initial={editor.detail.meta.application.status} />}
            <SyncBadge state={doc.sync} seconds={doc.compile?.seconds} />
            <div className="ml-auto flex shrink-0 items-center">
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button variant="ghost" size="icon" className="size-8" disabled={!doc.canUndo || doc.manual} onClick={doc.undo} aria-label="Annuler">
                    <Undo2 className="size-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Annuler <kbd className="ml-1 font-mono text-[10px] opacity-70">Ctrl Z</kbd></TooltipContent>
              </Tooltip>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button variant="ghost" size="icon" className="size-8" disabled={!doc.canRedo || doc.manual} onClick={doc.redo} aria-label="Rétablir">
                    <Redo2 className="size-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Rétablir <kbd className="ml-1 font-mono text-[10px] opacity-70">Ctrl Y</kbd></TooltipContent>
              </Tooltip>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button size="sm" className="ml-1.5 h-8 gap-1.5 text-[12.5px]" disabled={!url} aria-label="Télécharger">
                    <Download className="size-3.5" />
                    <span className="hidden @xl:inline">Télécharger</span>
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-56">
                  <DropdownMenuItem asChild>
                    <a href={url ?? undefined} download={`${stem}.pdf`}>
                      <FileText className="size-3.5" />
                      Le CV en PDF
                    </a>
                  </DropdownMenuItem>
                  <DropdownMenuItem asChild>
                    <a href={api.texUrl(slug)} download={`${stem}.tex`}>
                      <FileCode2 className="size-3.5" />
                      Son code LaTeX (.tex)
                    </a>
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </header>

          <ScoreBand
            slug={slug}
            pdfVersion={editor.pdfVersion}
            content={editor.content}
            update={editor.update}
            locked={editor.manual}
            onReveal={revealField}
            onOffer={() => setTab('offer')}
          />

          {editor.manual && !onLetter && (
            <div role="status" className="flex shrink-0 items-center gap-2 border-b border-warning/30 bg-warning/10 px-4 py-2 text-[12px]">
              <Lock className="size-3.5 shrink-0 text-warning" />
              <span className="min-w-0 flex-1">
                <span className="font-medium">Mode manuel.</span> Ce CV suit son code LaTeX : le contenu et le style sont verrouillés.
              </span>
              <Button variant="outline" size="sm" className="h-7 shrink-0 bg-background text-[12px]" onClick={() => setLeaving(true)}>
                Revenir au mode visuel
              </Button>
            </div>
          )}

          <Tabs value={tab} onValueChange={(value) => setTab(value as Tab)} className="flex min-h-0 flex-1 flex-col gap-0">
            <div className="shrink-0 border-b px-4 py-2">
              <TabsList className="h-8">
                {TABS.map(([value, label]) => (
                  <TabsTrigger key={value} value={value} className="px-2.5 text-[12px]">{label}</TabsTrigger>
                ))}
              </TabsList>
            </div>
            <TabsContent value="content" className="min-h-0 flex-1">
              {editor.content ? (
                <ContentEditor content={editor.content} update={editor.update} focus={focus} locked={editor.manual} oneColumn={editor.style?.columns.layout === 'one'} />
              ) : (
                <Locked editor={editor}>
                  <EditorSkeleton />
                </Locked>
              )}
            </TabsContent>
            <TabsContent value="style" className="min-h-0 flex-1">
              <Locked editor={editor}>
                {editor.style && editor.content ? (
                  <StyleEditor slug={slug} style={editor.style} content={editor.content} editor={editor} />
                ) : (
                  <EditorSkeleton />
                )}
              </Locked>
            </TabsContent>
            <TabsContent value="offer" className="min-h-0 flex-1">
              <ScrollArea className="h-full">
                <OfferTab
                  slug={slug}
                  pdfVersion={editor.pdfVersion}
                />
              </ScrollArea>
            </TabsContent>
            <TabsContent value="letter" className="min-h-0 flex-1">
              <LetterTab slug={slug} letter={letter} />
            </TabsContent>
            <TabsContent value="latex" className="min-h-0 flex-1">
              <Suspense
                fallback={
                  <div className="flex h-full items-center justify-center text-muted-foreground">
                    <Loader2 className="size-5 animate-spin" />
                  </div>
                }
              >
                <LatexTab
                  adapter={{
                    key: `${slug}:${editor.pdfVersion}:${editor.manual}`,
                    load: cvSource,
                    save: saveCvSource,
                    onSaved: (result) => {
                      editor.applyCompile(result.compile)
                      editor.setMode(result.mode)
                    },
                    recompile: editor.recompile,
                    manual: editor.manual,
                    locked: slug === 'base' && !editor.manual ? 'La version classique reste en mode visuel : duplique-la pour modifier son code.' : null,
                    compile: editor.compile,
                    texUrl: api.texUrl(slug),
                    fileName: `${editor.detail?.file_stem ?? slug}.tex`,
                    texts: {
                      generated: 'Généré depuis le contenu et le style. Le modifier puis compiler passe ce CV en mode manuel.',
                      manual: 'Ce code est la source du CV.',
                      confirmTitle: 'Passer ce CV en mode manuel ?',
                      confirmText:
                        'Ton code LaTeX devient la source de ce CV. Les onglets Contenu et Style seront verrouillés pour ce CV. Tu pourras revenir au mode visuel, mais tes modifications du code seront alors perdues.',
                    },
                  }}
                />
              </Suspense>
            </TabsContent>
            <TabsContent value="ats" className="min-h-0 flex-1">
              <ScrollArea className="h-full">
                <AtsTab slug={slug} pdfVersion={editor.pdfVersion} />
              </ScrollArea>
            </TabsContent>
          </Tabs>
        </div>
      </ResizablePanel>
      <ResizableHandle withHandle />
      <ResizablePanel id="preview" defaultSize="52%" minSize="30%">
        {onLetter ? (
          <PdfPreview
            key="letter"
            url={letter.pdfVersion ? api.letterPdfUrl(slug, letter.pdfVersion) : null}
            sync={letter.sync}
            compile={letter.compile}
            pages={null}
            downloadName={`${letter.state?.file_stem ?? 'lettre'}.pdf`}
            document="La lettre"
            empty={letter.state && !letter.letter ? "L'aperçu de la lettre s'affiche ici une fois qu'elle est écrite." : undefined}
          />
        ) : (
          <PdfPreview
            key="cv"
            url={url}
            sync={editor.sync}
            compile={editor.compile}
            pages={editor.detail?.meta.pages ?? null}
            downloadName={`${editor.detail?.file_stem ?? slug}.pdf`}
            onCut={editor.manual ? undefined : (cut: Cut) => editor.update((draft) => void applyCut(draft, cut.id))}
            onPick={editor.manual ? undefined : (point) => void pick(point)}
            highlight={highlight}
          />
        )}
      </ResizablePanel>

      <AlertDialog open={leaving} onOpenChange={setLeaving}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Revenir au mode visuel ?</AlertDialogTitle>
            <AlertDialogDescription>
              Le code LaTeX sera refait à partir du contenu et du style : tes modifications faites dans le code seront perdues.
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
    </ResizablePanelGroup>
  )
}

/** Le statut de la candidature, modifiable sans quitter le CV. */
function StatusMenu({ slug, initial }: { slug: string; initial: ApplicationStatus }) {
  const [status, setStatus] = useState(initial)
  const choose = async (next: ApplicationStatus) => {
    const before = status
    setStatus(next)
    try {
      await api.updateApplication(slug, { status: next })
    } catch (error) {
      setStatus(before)
      toast.error('Statut non enregistré', { description: (error as Error).message })
    }
  }
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={`Statut de la candidature : ${STATUS[status].label}`}
          className={cn('flex h-6 shrink-0 items-center gap-1 rounded-full pr-1.5 pl-2 text-[11.5px] font-medium transition-opacity hover:opacity-85', STATUS[status].pill)}
        >
          {STATUS[status].label}
          <ChevronDown className="size-3" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-48">
        <DropdownMenuLabel className="text-[11px] text-muted-foreground">Statut de la candidature</DropdownMenuLabel>
        {STATUS_ORDER.map((value) => (
          <DropdownMenuItem key={value} onSelect={() => void choose(value)}>
            <span className={cn('size-2 rounded-full', STATUS[value].dot)} />
            {STATUS[value].label}
            {value === status && <Check className="ml-auto size-3.5" />}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

/** Contenu et Style : verrouillés en mode manuel (le code LaTeX fait foi). */
function Locked({ editor, children }: { editor: CvEditor; children: React.ReactNode }) {
  return (
    <ScrollArea className="h-full">
      <fieldset
        disabled={editor.manual}
        aria-label={editor.manual ? 'Verrouillé en mode manuel' : undefined}
        className={cn('mx-auto block max-w-2xl min-w-0 px-5 py-5', editor.manual && 'pointer-events-none opacity-55 select-none')}
      >
        {children}
      </fieldset>
    </ScrollArea>
  )
}

const SYNC_TEXT: Record<SyncState, string> = {
  loading: 'Chargement…',
  pending: 'Modifications…',
  saving: 'Enregistrement…',
  compiling: 'Compilation…',
  ready: 'Enregistré',
  error: 'Erreur',
}

function SyncBadge({ state, seconds }: { state: SyncState; seconds?: number }) {
  const busy = state === 'saving' || state === 'compiling' || state === 'loading'
  return (
    <span
      role="status"
      className={cn(
        'flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[11px] whitespace-nowrap transition-colors',
        state === 'error' ? 'bg-destructive/10 text-destructive' : 'text-muted-foreground',
      )}
    >
      {busy && <Loader2 className="size-3 animate-spin" />}
      {state === 'ready' && <CheckCircle2 className="size-3 text-success" />}
      {state === 'pending' && <span className="size-1.5 rounded-full bg-warning" />}
      {state === 'error' && <CircleAlert className="size-3" />}
      {SYNC_TEXT[state]}
      {state === 'ready' && seconds ? <span className="hidden tabular-nums opacity-70 @2xl:inline">· {seconds.toFixed(1).replace('.', ',')} s</span> : null}
    </span>
  )
}

function EditorSkeleton() {
  return (
    <div className="flex flex-col gap-3">
      <Skeleton className="h-4 w-24" />
      <Skeleton className="h-48 w-full rounded-xl" />
      <Skeleton className="h-4 w-32" />
      {[0, 1, 2].map((i) => <Skeleton key={i} className="h-11 w-full rounded-xl" />)}
    </div>
  )
}
