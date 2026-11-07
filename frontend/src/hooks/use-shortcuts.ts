import { useEffect } from 'react'

interface Shortcuts {
  undo: () => void
  redo: () => void
  save: () => void
}

/**
 * Ctrl+Z annuler, Ctrl+Y ou Ctrl+Maj+Z rétablir, Ctrl+S enregistrer
 * (Cmd sur Mac). Ils remplacent l'annulation propre à chaque champ : une seule
 * histoire pour tout le CV.
 */
export function useShortcuts({ undo, redo, save }: Shortcuts) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey) || event.altKey) return
      // L'éditeur de code a ses propres annuler, rétablir et enregistrer.
      if (event.target instanceof Element && event.target.closest('.monaco-editor')) return
      const key = event.key.toLowerCase()
      if (key === 'z' && !event.shiftKey) {
        event.preventDefault()
        undo()
      } else if (key === 'y' || (key === 'z' && event.shiftKey)) {
        event.preventDefault()
        redo()
      } else if (key === 's') {
        event.preventDefault()
        save()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [undo, redo, save])
}
