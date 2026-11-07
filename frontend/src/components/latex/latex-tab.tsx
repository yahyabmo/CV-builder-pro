import Editor, { type OnMount } from '@monaco-editor/react'
import { CircleAlert, Download, Loader2, Lock, Play, RotateCcw } from 'lucide-react'
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'

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
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useTheme } from '@/hooks/use-theme'
import type { LatexError } from '@/lib/types'

import type { LatexAdapter } from './adapter'
import { monaco } from './monaco'

type CodeEditor = Parameters<OnMount>[0]

/**
 * Le code LaTeX d'un document (le CV ou sa lettre). En mode visuel, c'est le code
 * généré ; le modifier puis compiler fait passer le document en mode manuel (après
 * confirmation). En mode manuel, ce code est sa source.
 */
export default function LatexTab({ adapter }: { adapter: LatexAdapter }) {
  const { resolved } = useTheme()
  const [source, setSource] = useState<string | null>(null)
  const [value, setValue] = useState('')
  const [busy, setBusy] = useState(false)
  const [asking, setAsking] = useState(false)
  const code = useRef<CodeEditor | null>(null)
  const dirty = source !== null && value !== source
  const locked = adapter.locked !== null

  // Le code suit les modifications faites dans Contenu et Style, tant qu'on n'y touche pas ici.
  const dirtyRef = useRef(dirty)
  useLayoutEffect(() => {
    dirtyRef.current = dirty
  }, [dirty])
  const { load } = adapter
  useEffect(() => {
    if (dirtyRef.current) return
    let cancelled = false
    load().then(
      (found) => {
        if (cancelled) return
        setSource(found.tex)
        setValue(found.tex)
      },
      (error: Error) => toast.error('Code LaTeX indisponible', { description: error.message }),
    )
    return () => {
      cancelled = true
    }
  }, [load, adapter.key])

  // Les erreurs de la dernière compilation (d'ici ou du mode visuel), au bon endroit dans le code.
  const errors: LatexError[] = useMemo(() => (adapter.compile && !adapter.compile.ok ? adapter.compile.errors : []), [adapter.compile])
  useEffect(() => {
    const model = code.current?.getModel()
    if (!model) return
    monaco.editor.setModelMarkers(
      model,
      'latex',
      errors
        .filter((e) => e.line != null && e.line <= model.getLineCount())
        .map((e) => ({
          startLineNumber: e.line as number,
          endLineNumber: e.line as number,
          startColumn: 1,
          endColumn: model.getLineMaxColumn(e.line as number),
          message: e.message,
          severity: monaco.MarkerSeverity.Error,
        })),
    )
  }, [errors, value])

  const save = useCallback(async () => {
    setBusy(true)
    try {
      const result = await adapter.save(code.current?.getValue() ?? value)
      adapter.onSaved(result)
      setSource(code.current?.getValue() ?? value)
      if (result.compile.ok) toast.success(result.mode === 'manual' ? 'Code compilé (mode manuel)' : 'Compilé')
      else toast.error('Erreur LaTeX', { description: result.compile.errors[0]?.message })
    } catch (error) {
      toast.error('Compilation impossible', { description: (error as Error).message })
    } finally {
      setBusy(false)
    }
  }, [value, adapter])

  // Compiler : en mode visuel, un code modifié demande d'abord confirmation.
  const latest = useRef({ dirty, manual: adapter.manual, save, recompile: adapter.recompile })
  useLayoutEffect(() => {
    latest.current = { dirty, manual: adapter.manual, save, recompile: adapter.recompile }
  })
  const compile = useCallback(() => {
    const { dirty: changed, manual, save: run, recompile } = latest.current
    if (!changed && !manual) recompile()
    else if (!manual) setAsking(true)
    else void run()
  }, [])

  const mount: OnMount = (instance) => {
    code.current = instance
    instance.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, compile)
    instance.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, compile)
  }

  const reveal = (line: number) => {
    const instance = code.current
    if (!instance) return
    instance.revealLineInCenter(line)
    instance.setPosition({ lineNumber: line, column: 1 })
    instance.focus()
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-b px-4 py-2">
        {adapter.manual ? (
          <Badge variant="outline" className="h-5 border-warning/50 text-[10.5px] text-warning">mode manuel</Badge>
        ) : (
          <Badge variant="secondary" className="h-5 text-[10.5px]">généré</Badge>
        )}
        <span className="min-w-0 flex-1 truncate text-[11.5px] text-muted-foreground">
          {adapter.locked ?? (adapter.manual ? adapter.texts.manual : adapter.texts.generated)}
        </span>
        {dirty && (
          <Button variant="ghost" size="sm" className="h-7 gap-1 px-2 text-[12px] text-muted-foreground" onClick={() => source != null && setValue(source)}>
            <RotateCcw className="size-3.5" /> Annuler
          </Button>
        )}
        <Button variant="ghost" size="icon" className="size-7" asChild aria-label="Télécharger le .tex">
          <a href={adapter.texUrl} download={adapter.fileName}>
            <Download className="size-3.5" />
          </a>
        </Button>
        <Button size="sm" className="h-7 gap-1.5 text-[12px]" onClick={compile} disabled={busy || (locked && dirty)}>
          {busy ? <Loader2 className="size-3.5 animate-spin" /> : <Play className="size-3.5" />} Compiler
          <kbd className="ml-0.5 font-mono text-[10px] opacity-70">Ctrl S</kbd>
        </Button>
      </div>

      <div className="relative min-h-0 flex-1">
        {source === null ? (
          <div className="flex h-full items-center justify-center text-muted-foreground">
            <Loader2 className="size-5 animate-spin" />
          </div>
        ) : (
          <Editor
            language="latex"
            theme={resolved === 'dark' ? 'cvb-dark' : 'cvb-light'}
            value={value}
            onChange={(next) => setValue(next ?? '')}
            onMount={mount}
            loading={<Loader2 className="size-5 animate-spin text-muted-foreground" />}
            options={{
              readOnly: locked,
              fontFamily: "'Geist Mono Variable', ui-monospace, monospace",
              fontSize: 12.5,
              lineHeight: 19,
              minimap: { enabled: false },
              wordWrap: 'on',
              scrollBeyondLastLine: false,
              automaticLayout: true,
              tabSize: 2,
              padding: { top: 10 },
              renderLineHighlight: 'line',
              smoothScrolling: true,
            }}
          />
        )}
        {locked && (
          <span className="pointer-events-none absolute top-2 right-4 flex items-center gap-1 rounded-md bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
            <Lock className="size-3" /> lecture seule
          </span>
        )}
      </div>

      {errors.length > 0 && (
        <ul className="max-h-36 shrink-0 overflow-y-auto border-t bg-destructive/5 px-4 py-2 text-[12px]" aria-label="Erreurs LaTeX">
          {errors.map((error, i) => (
            <li key={i}>
              <button
                type="button"
                disabled={error.line == null}
                onClick={() => error.line != null && reveal(error.line)}
                className="flex w-full items-start gap-1.5 rounded px-1 py-0.5 text-left hover:bg-destructive/10 disabled:hover:bg-transparent"
              >
                <CircleAlert className="mt-0.5 size-3.5 shrink-0 text-destructive" />
                {error.line != null && <span className="shrink-0 font-mono text-muted-foreground">ligne {error.line}</span>}
                <span>{error.message}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      <AlertDialog open={asking} onOpenChange={setAsking}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{adapter.texts.confirmTitle}</AlertDialogTitle>
            <AlertDialogDescription>{adapter.texts.confirmText}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Annuler</AlertDialogCancel>
            <AlertDialogAction onClick={() => void save()}>Passer en mode manuel et compiler</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
