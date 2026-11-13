import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import { api } from '@/lib/api'
import type { CloneShape, CompileResult, CVContent, CVDetail, CVMode, CVStyle } from '@/lib/types'
import { useHistory } from './use-history'

// L'état d'enregistrement affiché dans la barre de l'éditeur.
export type SyncState = 'loading' | 'pending' | 'saving' | 'compiling' | 'ready' | 'error'

// Délai après la dernière modification avant d'enregistrer et de compiler.
const DEBOUNCE_MS = 450

/** Ce que l'historique suit : le contenu et la forme, ensemble. */
interface Doc {
  content: CVContent
  style: CVStyle
}

/**
 * L'édition d'un CV : contenu et style avec un historique commun, sauvegarde
 * automatique et compilation après chaque pause.
 *
 * Le composant qui l'utilise est remonté à chaque changement de CV (clé =
 * identifiant) : les références ci-dessous appartiennent à un seul CV, et un
 * enregistrement encore en cours finit sur le bon CV.
 */
export function useCvEditor(slug: string) {
  const history = useHistory<Doc | null>(null)
  const { reset: resetHistory, set: setHistory } = history
  const [detail, setDetail] = useState<CVDetail | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [sync, setSync] = useState<SyncState>('loading')
  const [compile, setCompile] = useState<CompileResult | null>(null)
  const [pdfVersion, setPdfVersion] = useState<number | null>(null)
  const [photoVersion, setPhotoVersion] = useState<number>(0)

  const saved = useRef<Doc | null>(null)
  const latest = useRef<Doc | null>(null)
  const running = useRef(false)
  const again = useRef(false)

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
          const doc = latest.current
          if (!doc) break
          if (doc !== saved.current) {
            setSync('saving')
            const before = saved.current
            if (!before || doc.content !== before.content) await api.saveContent(slug, doc.content)
            if (!before || doc.style !== before.style) await api.saveStyle(slug, doc.style)
            saved.current = doc
            compileNeeded = true
          }
          if (compileNeeded) {
            compileNeeded = false
            setSync('compiling')
            const result = await api.compile(slug)
            if (!result.superseded) {
              setCompile(result)
              if (result.ok) setPdfVersion(result.pdf_version)
            }
          }
        } while (again.current || latest.current !== saved.current)
        setSync('ready')
      } catch (error) {
        setSync('error')
        toast.error("L'enregistrement a échoué", {
          description: error instanceof Error ? error.message : String(error),
        })
      } finally {
        running.current = false
      }
    },
    [slug],
  )

  // Chargement du CV.
  useEffect(() => {
    let cancelled = false
    api
      .getCV(slug)
      .then((loaded) => {
        if (cancelled) return
        const doc = { content: loaded.content, style: loaded.style }
        setDetail(loaded)
        saved.current = doc
        latest.current = doc
        resetHistory(doc)
        setPdfVersion(loaded.pdf_version)
        setSync('ready')
        if (!loaded.pdf_version) void run(true)
      })
      .catch((error: Error) => {
        if (!cancelled) setLoadError(error.message)
      })
    return () => {
      cancelled = true
    }
  }, [slug, resetHistory, run])

  // Sauvegarde et compilation après une pause.
  useEffect(() => {
    latest.current = history.value
    if (!history.value || history.value === saved.current) return
    setSync('pending')
    const timer = window.setTimeout(() => void run(), DEBOUNCE_MS)
    return () => window.clearTimeout(timer)
  }, [history.value, run])

  // En quittant ce CV, une modification pas encore enregistrée l'est quand même.
  useEffect(
    () => () => {
      const doc = latest.current
      const before = saved.current
      if (!doc || doc === before || running.current) return
      if (!before || doc.content !== before.content) void api.saveContent(slug, doc.content)
      if (!before || doc.style !== before.style) void api.saveStyle(slug, doc.style)
    },
    [slug],
  )

  const saveNow = useCallback(() => {
    void run(true).then(() => toast.success('Enregistré'))
  }, [run])

  /** Modifie le contenu à partir d'une copie ; `group` regroupe les frappes. */
  const update = useCallback(
    (mutate: (draft: CVContent) => void, group: string | null = null) => {
      const current = latest.current
      if (!current) return
      const content = structuredClone(current.content)
      mutate(content)
      const doc = { ...current, content }
      latest.current = doc
      setHistory(doc, group)
    },
    [setHistory],
  )

  /** Modifie le style ; `group` regroupe les réglages successifs d'un même contrôle. */
  const updateStyle = useCallback(
    (mutate: (draft: CVStyle) => void, group: string | null = null) => {
      const current = latest.current
      if (!current) return
      const style = structuredClone(current.style)
      mutate(style)
      const doc = { ...current, style }
      latest.current = doc
      setHistory(doc, group)
    },
    [setHistory],
  )

  /** Remplace tout le style (thème appliqué) : une seule étape d'historique. */
  const replaceStyle = useCallback(
    (style: CVStyle) => {
      const current = latest.current
      if (!current) return
      const doc = { ...current, style: structuredClone(style) }
      latest.current = doc
      setHistory(doc, null)
    },
    [setHistory],
  )

  /** Une compilation faite ailleurs (onglet LaTeX) : l'aperçu la suit. */
  const applyCompile = useCallback((result: CompileResult) => {
    if (result.superseded) return
    setCompile(result)
    if (result.ok) setPdfVersion(result.pdf_version)
  }, [])

  /** Le mode a changé (passage en mode manuel, ou retour au visuel). */
  const setMode = useCallback((mode: CVMode) => {
    setDetail((current) => (current ? { ...current, meta: { ...current.meta, mode } } : current))
  }, [])

  /** La forme d'un CV cloné : celle de son PDF d'origine, ou la mise en page de l'appli. */
  const setShape = useCallback(
    async (shape: CloneShape) => {
      // Une frappe pas encore enregistrée part d'abord : la compilation la prend.
      await run(false)
      const result = await api.setShape(slug, shape)
      setDetail((current) => (current ? { ...current, shape } : current))
      applyCompile(result)
    },
    [slug, run, applyCompile],
  )

  /** Importe une photo (déjà recadrée) : elle remplace celle du CV. */
  const uploadPhoto = useCallback(
    async (file: Blob) => {
      const answer = await api.uploadPhoto(slug, file)
      setPhotoVersion(answer.version)
      // Le serveur a pointé content.header.photo vers le nouveau fichier ; la
      // copie locale suit comme une modification ordinaire (une frappe pas
      // encore enregistrée n'est pas perdue). Même nom de fichier : on
      // recompile seulement.
      if (latest.current && latest.current.content.header.photo !== answer.photo) {
        update((draft) => void (draft.header.photo = answer.photo))
      }
      await run(true)
    },
    [slug, run, update],
  )

  return {
    detail,
    loadError,
    content: history.value?.content ?? null,
    style: history.value?.style ?? null,
    update,
    updateStyle,
    replaceStyle,
    uploadPhoto,
    photoVersion,
    undo: history.undo,
    redo: history.redo,
    canUndo: history.canUndo,
    canRedo: history.canRedo,
    sync,
    compile,
    pdfVersion,
    saveNow,
    recompile: () => void run(true),
    applyCompile,
    setMode,
    setShape,
    manual: detail?.meta.mode === 'manual',
  }
}

export type CvEditor = ReturnType<typeof useCvEditor>
