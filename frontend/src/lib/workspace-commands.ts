// Ce que la palette de commandes (Ctrl+K) demande à l'espace de travail
// ouvert : un évènement sur window, écouté par Workspace.

export const TABS = [
  ['content', 'Contenu'],
  ['style', 'Style'],
  ['offer', 'Offre'],
  ['letter', 'Lettre'],
  ['latex', 'LaTeX'],
  ['ats', 'ATS'],
] as const

export type Tab = (typeof TABS)[number][0]

export type WorkspaceCommand = { action: 'tab'; tab: Tab } | { action: 'compile' }

export const WORKSPACE_EVENT = 'cvb:workspace'
export const PALETTE_EVENT = 'cvb:palette'

export function sendWorkspace(command: WorkspaceCommand) {
  window.dispatchEvent(new CustomEvent(WORKSPACE_EVENT, { detail: command }))
}

export function openPalette() {
  window.dispatchEvent(new Event(PALETTE_EVENT))
}
