import { AlertTriangle, Download, FileWarning, Loader2, Maximize2, Minus, Plus, Scissors } from 'lucide-react'
import { memo, useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import workerSrc from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { SyncState } from '@/hooks/use-cv-editor'
import type { CompileResult, Cut, PageBox } from '@/lib/types'
import { cn } from '@/lib/utils'

pdfjs.GlobalWorkerOptions.workerSrc = workerSrc

const ZOOMS = [0.5, 0.67, 0.8, 1, 1.25, 1.5, 2]
// Largeur d'une page A4, en points.
const PAGE_WIDTH_PT = 595.28

interface PdfPreviewProps {
  url: string | null
  sync: SyncState
  compile: CompileResult | null
  // Nombre de pages connu avant toute compilation (meta.json).
  pages: number | null
  downloadName: string
  // Applique une coupe proposée quand le contenu déborde.
  onCut?: (cut: Cut) => void
  // « Le CV » ou « La lettre », dans les alertes.
  document?: string
  // Montré à la place de la page tant qu'il n'y a pas de PDF.
  empty?: React.ReactNode
  // Un clic sur la page : le point touché, en points depuis le haut gauche.
  onPick?: (point: { x: number; y: number }) => void
  // Un cadre à entourer un instant sur la page, en points.
  highlight?: PageBox | null
}

interface Ring {
  left: number
  top: number
  width: number
  height: number
}

export function PdfPreview({ url, sync, compile, pages: knownPages, downloadName, onCut, document = 'Le CV', empty, onPick, highlight }: PdfPreviewProps) {
  const frame = useRef<HTMLDivElement>(null)
  const stage = useRef<HTMLDivElement>(null)
  const [ring, setRing] = useState<Ring | null>(null)
  const [width, setWidth] = useState(0)
  const [zoom, setZoom] = useState(1)
  // Double tampon : deux documents restent montés ; le nouveau PDF se charge
  // dans celui qui est caché, et on bascule une fois sa page rendue. La page
  // affichée ne clignote jamais.
  const [slots, setSlots] = useState<[string | null, string | null]>([null, null])
  const [visible, setVisible] = useState<0 | 1>(0)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (!url) return
    setSlots((current) => {
      if (current[visible] === url || current[1 - visible] === url) return current
      const copy: [string | null, string | null] = [...current]
      copy[1 - visible] = url
      return copy
    })
  }, [url, visible])

  useEffect(() => {
    const element = frame.current
    if (!element) return
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width))
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  // Rappels stables : un rappel qui change à chaque rendu ferait redessiner les
  // pages PDF (et clignoter l'aperçu) à chaque changement d'état.
  const latest = useRef({ url, visible })
  useLayoutEffect(() => {
    latest.current = { url, visible }
  }, [url, visible])
  const onRendered = useCallback((slot: 0 | 1, file: string) => {
    setFailed(false)
    // Seul le PDF le plus récent passe devant : un ancien PDF re-rendu (zoom,
    // largeur) reste caché.
    if (file === latest.current.url && slot !== latest.current.visible) setVisible(slot)
  }, [])
  const onFailed = useCallback(() => setFailed(true), [])

  // Le cadre de l'élément touché, posé sur la page affichée, puis effacé.
  useEffect(() => {
    const page = stage.current?.querySelector<HTMLElement>('[data-front=true]')
    if (!highlight || !page) return
    const scale = page.clientWidth / PAGE_WIDTH_PT
    const frameId = window.requestAnimationFrame(() =>
      setRing({ left: page.offsetLeft + highlight.x * scale, top: page.offsetTop + highlight.y * scale, width: highlight.w * scale, height: highlight.h * scale }),
    )
    const timer = window.setTimeout(() => setRing(null), 2400)
    return () => {
      window.cancelAnimationFrame(frameId)
      window.clearTimeout(timer)
    }
  }, [highlight])

  const pick = (event: React.MouseEvent<HTMLDivElement>) => {
    const page = (event.target as HTMLElement).closest<HTMLElement>('[data-front=true]')
    if (!onPick || !page) return
    const box = page.getBoundingClientRect()
    const scale = PAGE_WIDTH_PT / box.width
    onPick({ x: (event.clientX - box.left) * scale, y: (event.clientY - box.top) * scale })
  }

  const pageWidth = Math.round(Math.max(240, (width - 48) * zoom))
  const shown = slots[visible]
  const pages = compile?.pages ?? knownPages
  const busy = sync === 'saving' || sync === 'compiling' || sync === 'pending'
  const zoomIndex = ZOOMS.indexOf(zoom)

  return (
    <div className="@container flex h-full flex-col bg-canvas">
      <div className="flex h-11 shrink-0 items-center gap-1 border-b bg-background/80 px-3 backdrop-blur">
        <span className="mr-auto flex min-w-0 items-center gap-2 text-[12px] text-muted-foreground">
          Aperçu
          {pages != null && (
            <span className={cn('shrink-0 tabular-nums', pages > 1 && 'font-medium text-warning')}>
              · {pages} page{pages > 1 ? 's' : ''}
            </span>
          )}
          {onPick && <span className="hidden truncate @[30rem]:inline">· clique un passage pour le modifier</span>}
          {busy && <Loader2 className="size-3.5 animate-spin" aria-label="Compilation en cours" />}
        </span>
        <Button variant="ghost" size="icon" className="size-7" aria-label="Zoom arrière" disabled={zoomIndex === 0} onClick={() => setZoom(ZOOMS[Math.max(0, zoomIndex - 1)])}>
          <Minus className="size-3.5" />
        </Button>
        <button
          type="button"
          className="w-12 rounded-md py-1 text-center text-[12px] tabular-nums text-muted-foreground hover:bg-muted"
          onClick={() => setZoom(1)}
          aria-label="Revenir à la largeur du panneau"
        >
          {Math.round(zoom * 100)} %
        </button>
        <Button variant="ghost" size="icon" className="size-7" aria-label="Zoom avant" disabled={zoomIndex === ZOOMS.length - 1} onClick={() => setZoom(ZOOMS[Math.min(ZOOMS.length - 1, zoomIndex + 1)])}>
          <Plus className="size-3.5" />
        </Button>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon" className="size-7" aria-label="Ajuster à la largeur" onClick={() => setZoom(1)}>
              <Maximize2 className="size-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Ajuster à la largeur</TooltipContent>
        </Tooltip>
        {url && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="icon" className="size-7" asChild>
                <a href={url} download={downloadName} aria-label="Télécharger le PDF">
                  <Download className="size-3.5" />
                </a>
              </Button>
            </TooltipTrigger>
            <TooltipContent>Télécharger le PDF</TooltipContent>
          </Tooltip>
        )}
      </div>

      {/* Place de la barre de défilement toujours réservée : sinon sa venue change
          la largeur, qui fait redessiner la page, qui fait partir la barre… */}
      <div ref={frame} className="relative min-h-0 flex-1 overflow-auto [scrollbar-gutter:stable]">
        <Notices compile={compile} onCut={onCut} document={document} />
        {/* Un clic sur la page mène au champ ; le clavier passe par le sommaire de l'éditeur. */}
        {/* eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions */}
        <div ref={stage} onClick={onPick ? pick : undefined} className={cn('relative flex min-h-full justify-center p-6', onPick && '[&_[data-front=true]]:cursor-pointer')}>
          {!shown && !failed && (!url && empty ? <div className="m-auto max-w-xs text-center text-[13px] text-muted-foreground">{empty}</div> : <PageSkeleton width={pageWidth} />)}
          {failed && !shown && (
            <div className="m-auto flex max-w-xs flex-col items-center gap-2 text-center text-[13px] text-muted-foreground">
              <FileWarning className="size-6" />
              Le PDF n'a pas pu être affiché.
            </div>
          )}
          {([0, 1] as const).map((slot) => {
            const file = slots[slot]
            if (!file) return null
            return (
              <PdfSlot
                key={slot}
                slot={slot}
                file={file}
                width={pageWidth}
                front={slot === visible && Boolean(shown)}
                onRendered={onRendered}
                onFailed={onFailed}
              />
            )
          })}
          {ring && (
            <div
              aria-hidden
              className="pointer-events-none absolute animate-in rounded-[3px] bg-primary/5 ring-2 ring-primary/70 fade-in"
              style={ring}
            />
          )}
        </div>
      </div>
    </div>
  )
}

interface PdfSlotProps {
  slot: 0 | 1
  file: string
  width: number
  front: boolean
  onRendered: (slot: 0 | 1, file: string) => void
  onFailed: () => void
}

/** Une page PDF ; ne se redessine que si son fichier ou sa largeur change. */
const PdfSlot = memo(function PdfSlot({ slot, file, width, front, onRendered, onFailed }: PdfSlotProps) {
  const rendered = useCallback(() => onRendered(slot, file), [onRendered, slot, file])
  return (
    <div
      aria-hidden={!front}
      data-pdf={file}
      data-front={front}
      // Hauteur fixée (A4) : pendant qu'une page se redessine, la mise en page
      // ne bouge pas.
      style={{ width, height: Math.round(width * Math.SQRT2) }}
      className={cn(front ? 'relative' : 'pointer-events-none absolute top-6 opacity-0')}
    >
      <Document
        file={file}
        loading={null}
        onLoadError={onFailed}
        className="shadow-[0_1px_2px_rgb(0_0_0/0.06),0_8px_24px_-6px_rgb(0_0_0/0.18)]"
      >
        <Page
          pageNumber={1}
          width={width}
          renderTextLayer={false}
          renderAnnotationLayer={false}
          loading={null}
          onRenderSuccess={rendered}
        />
      </Document>
    </div>
  )
})

function PageSkeleton({ width }: { width: number }) {
  return <Skeleton className="rounded-none" style={{ width, height: width * 1.4142 }} />
}

/** Erreurs LaTeX, page en trop, texte qui déborde : au-dessus de l'aperçu. */
function Notices({ compile, onCut, document }: { compile: CompileResult | null; onCut?: (cut: Cut) => void; document: string }) {
  if (!compile) return null
  if (!compile.ok && compile.errors.length > 0) {
    return (
      <div className="sticky top-0 z-10 p-3">
        <div className="rounded-lg border border-destructive/30 bg-background/95 p-3 shadow-sm backdrop-blur">
          <p className="flex items-center gap-2 text-[13px] font-medium text-destructive">
            <AlertTriangle className="size-4" />
            La compilation a échoué : l'aperçu montre la dernière version valide.
          </p>
          <ul className="mt-2 flex flex-col gap-1.5">
            {compile.errors.slice(0, 3).map((error, index) => (
              <li key={index} className="text-[12px]">
                {error.line != null && <span className="mr-1.5 font-mono text-muted-foreground">ligne {error.line}</span>}
                {error.message}
                {error.context && (
                  <code className="mt-1 block truncate rounded bg-muted px-2 py-1 font-mono text-[11px] text-muted-foreground">
                    {error.context}
                  </code>
                )}
              </li>
            ))}
          </ul>
        </div>
      </div>
    )
  }
  const warnings: string[] = []
  if (compile.overflow_pt > 0)
    warnings.push(`Le contenu dépasse le bas de la page de ${Math.round(compile.overflow_pt)} pt : raccourcis un texte, masque une section ou coupe :`)
  if (compile.pages != null && compile.pages > 1) warnings.push(`${document} fait ${compile.pages} pages au lieu d'une.`)
  if (warnings.length === 0) return null
  return (
    <div className="sticky top-0 z-10 p-3">
      <div className="flex items-start gap-2 rounded-lg border border-warning/40 bg-background/95 p-3 text-[12px] shadow-sm backdrop-blur">
        <AlertTriangle className="mt-px size-4 shrink-0 text-warning" />
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          {warnings.map((w) => <span key={w}>{w}</span>)}
          {onCut && compile.cuts.length > 0 && (
            <ul className="mt-1 flex flex-col gap-1">
              {compile.cuts.map((cut) => (
                <li key={cut.id}>
                  <button
                    type="button"
                    onClick={() => onCut(cut)}
                    className="flex w-full items-center gap-1.5 rounded-md px-1.5 py-1 text-left hover:bg-muted"
                    title={cut.detail}
                  >
                    <Scissors className="size-3.5 shrink-0 text-muted-foreground" />
                    <span className="truncate">{cut.label}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}
