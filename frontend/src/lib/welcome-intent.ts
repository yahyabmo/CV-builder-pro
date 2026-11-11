// Ce que l'écran de départ fabrique : un CV classique de plus (« new ») ou un nouveau
// contenu pour un CV classique existant (« replace »). Gardé le temps de l'import ou de
// la saisie (sessionStorage : un onglet), effacé une fois le CV validé ou l'envoi annulé.
// Sans intention : le premier lancement, qui remplace la première version.

export type WelcomeIntent = { mode: 'new'; name: string } | { mode: 'replace'; target: string; name: string }

const KEY = 'cv-builder.welcome-intent'
let memory: WelcomeIntent | null = null

export function readIntent(): WelcomeIntent | null {
  try {
    const raw = sessionStorage.getItem(KEY)
    return raw ? (JSON.parse(raw) as WelcomeIntent) : null
  } catch {
    return memory
  }
}

export function setIntent(intent: WelcomeIntent): void {
  memory = intent
  try {
    sessionStorage.setItem(KEY, JSON.stringify(intent))
  } catch {
    /* gardée en mémoire pour cette page */
  }
}

export function clearIntent(): void {
  memory = null
  try {
    sessionStorage.removeItem(KEY)
  } catch {
    /* rien à effacer */
  }
}

/** Les champs de POST /api/welcome/apply qui disent où va le CV. */
export function intentFields(intent: WelcomeIntent | null): { new_name?: string; target?: string } {
  if (intent?.mode === 'new') return { new_name: intent.name }
  if (intent?.mode === 'replace') return { target: intent.target }
  return {}
}
