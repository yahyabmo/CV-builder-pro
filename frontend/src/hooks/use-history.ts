import { useCallback, useReducer } from 'react'

// Historique annuler / rétablir d'une valeur.
//
// Les frappes successives dans un même champ (même `group`) à moins d'une
// seconde d'intervalle forment une seule étape : Ctrl+Z annule le mot ou la
// phrase, pas chaque lettre.

const GROUP_WINDOW_MS = 1000
const LIMIT = 200

interface State<T> {
  past: T[]
  present: T
  future: T[]
  group: string | null
  at: number
}

type Action<T> =
  | { type: 'set'; value: T; group: string | null; at: number }
  | { type: 'undo' }
  | { type: 'redo' }
  | { type: 'reset'; value: T }

function reducer<T>(state: State<T>, action: Action<T>): State<T> {
  switch (action.type) {
    case 'set': {
      if (Object.is(action.value, state.present)) return state
      const sameGroup =
        action.group !== null &&
        action.group === state.group &&
        action.at - state.at < GROUP_WINDOW_MS
      return {
        past: sameGroup ? state.past : [...state.past, state.present].slice(-LIMIT),
        present: action.value,
        future: [],
        group: action.group,
        at: action.at,
      }
    }
    case 'undo': {
      const previous = state.past.at(-1)
      if (previous === undefined) return state
      return {
        past: state.past.slice(0, -1),
        present: previous,
        future: [state.present, ...state.future],
        group: null,
        at: 0,
      }
    }
    case 'redo': {
      const [next, ...rest] = state.future
      if (next === undefined) return state
      return { past: [...state.past, state.present], present: next, future: rest, group: null, at: 0 }
    }
    case 'reset':
      return { past: [], present: action.value, future: [], group: null, at: 0 }
  }
}

export function useHistory<T>(initial: T) {
  const [state, dispatch] = useReducer(reducer<T>, {
    past: [],
    present: initial,
    future: [],
    group: null,
    at: 0,
  })
  const set = useCallback(
    (value: T, group: string | null = null) =>
      dispatch({ type: 'set', value, group, at: Date.now() }),
    [],
  )
  const undo = useCallback(() => dispatch({ type: 'undo' }), [])
  const redo = useCallback(() => dispatch({ type: 'redo' }), [])
  const reset = useCallback((value: T) => dispatch({ type: 'reset', value }), [])
  return {
    value: state.present,
    set,
    undo,
    redo,
    reset,
    canUndo: state.past.length > 0,
    canRedo: state.future.length > 0,
  }
}
