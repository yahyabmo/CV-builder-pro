import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import { api } from '@/lib/api'
import type { CompileResult, LetterContent, LetterState } from '@/lib/types'
import type { SyncState } from './use-cv-editor'
import { useHistory } from './use-history'

const DEBOUNCE_MS = 450

/**
 * La lettre de motivation d'un CV : chargée à la première ouverture de l'onglet,
 * avec son propre historique, enregistrée puis compilée après chaque pause.
 * `cvVersion` : la version du PDF du CV, dont la lettre reprend le haut.
 */
export function useLetterEditor(slug: string, active: boolean, cvVersion: number | null) {
  const history = useHistory<LetterContent | null>(null)
  const { reset: resetHistory, set: setHistory } = history
  const [state, setState] = useState<LetterState | null>(null)
  const [sync, setSync] = useState<SyncState>('loading')
  const [compile, setCompile] = useState<CompileResult | null>(null)
  const [pdfVersion, setPdfVersion] = useState<number | null>(null)
  const [generating, setGenerating] = useState(false)

  const saved = useRef<LetterContent | null>(null)
  const latest = useRef<LetterContent | null>(null)
  const running = useRef(false)
  const again = useRef(false)
  const loaded = useRef(false)

  const applyCompile = useCallback((result: CompileResult) => {
    if (result.superseded) return
    setCompile(result)
    if (result.ok) setPdfVersion(result.pdf_version)
  }, [])

  const run = useCallback(
    async (forceCompile = false) => {
      if (running.current) {
        again.current = true
        return
      }
      running.current = true
      let compileNeeded = forceCompile
      try {
        do {
          again.current = false
          const letter = latest.current
          if (!letter) break
          if (letter !== saved.current) {
            setSync('saving')
            setState(await api.saveLetter(slug, letter))
            saved.current = letter
            compileNeeded = true
          }
          if (compileNeeded) {
            compileNeeded = false
            setSync('compiling')
            applyCompile(await api.compileLetter(slug))
          }
        } while (again.current || latest.current !== saved.current)
        setSync('ready')
      } catch (error) {
        setSync('error')
        toast.error("La lettre n'a pas été enregistrée", { description: (error as Error).message })
      } finally {
        running.current = false
      }
    },
    [slug, applyCompile],
  )

  // Chargement à la première ouverture de l'onglet.
  useEffect(() => {
    if (!active || loaded.current) return
    loaded.current = true
    api.letter(slug).then(
      (found) => {
        setState(found)
        saved.current = found.letter
        latest.current = found.letter
        resetHistory(found.letter)
        setPdfVersion(found.pdf_version)
        setSync('ready')
      },
      (error: Error) => {
        setSync('error')
        toast.error('Lettre indisponible', { description: error.message })
      },
    )
  }, [active, slug, resetHistory, run])

  // Le nom, les coordonnées et la couleur viennent du CV : une lettre sans PDF,
  // ou plus ancienne que le dernier PDF du CV, est recompilée à l'ouverture.
  const mode = history.value?.mode
  useEffect(() => {
    if (!active || mode !== 'visual') return
    if (pdfVersion !== null && (cvVersion === null || pdfVersion >= cvVersion)) return
    const timer = window.setTimeout(() => void run(true), 0)
    return () => window.clearTimeout(timer)
  }, [active, mode, cvVersion, pdfVersion, run])

  // Enregistrement et compilation après une pause.
  useEffect(() => {
    latest.current = history.value
    if (!history.value || history.value === saved.current) return
    setSync('pending')
    const timer = window.setTimeout(() => void run(), DEBOUNCE_MS)
    return () => window.clearTimeout(timer)
  }, [history.value, run])

  /** Modifie la lettre à partir d'une copie ; `group` regroupe les frappes. */
  const update = useCallback(
    (mutate: (draft: LetterContent) => void, group: string | null = null) => {
      const current = latest.current
      if (!current) return
      const letter = structuredClone(current)
      mutate(letter)
      latest.current = letter
      setHistory(letter, group)
    },
    [setHistory],
  )

  /** Écrit (ou réécrit) la lettre avec l'IA : elle remplace la précédente. */
  const generate = useCallback(
    async (why: string, detail: string) => {
      setGenerating(true)
      try {
        const result = await api.generateLetter(slug, why, detail)
        setState(result.state)
        saved.current = result.state.letter
        latest.current = result.state.letter
        resetHistory(result.state.letter)
        applyCompile(result.compile)
        setSync('ready')
        return true
      } catch (error) {
        toast.error('Lettre non générée', { description: (error as Error).message })
        return false
      } finally {
        setGenerating(false)
      }
    },
    [slug, resetHistory, applyCompile],
  )

  /** Relit la lettre (après un passage en mode manuel ou un retour au visuel). */
  const refresh = useCallback(() => {
    api.letter(slug).then((found) => {
      setState(found)
      saved.current = found.letter
      latest.current = found.letter
      resetHistory(found.letter)
      setPdfVersion(found.pdf_version)
    }, () => undefined)
  }, [slug, resetHistory])

  const letter = history.value
  return {
    state,
    letter,
    available: state?.available ?? false,
    manual: letter?.mode === 'manual',
    update,
    generate,
    generating,
    undo: history.undo,
    redo: history.redo,
    canUndo: history.canUndo,
    canRedo: history.canRedo,
    sync,
    compile,
    pdfVersion,
    applyCompile,
    refresh,
    saveNow: () => void run(true),
    recompile: () => void run(true),
  }
}

export type LetterEditor = ReturnType<typeof useLetterEditor>
