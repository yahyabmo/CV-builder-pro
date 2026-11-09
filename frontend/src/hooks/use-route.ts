import { useCallback, useEffect, useState } from 'react'

// Navigation par l'adresse (#/…) : le bouton Précédent du navigateur marche,
// et une page se rouvre telle quelle après un rechargement.
//   #/cvs            Candidatures
//   #/library        Bibliothèque
//   #/cv/<slug>      un CV ouvert dans l'éditeur
//   #/target         cibler une offre (#/target/<slug> : à partir de ce CV)
//   #/settings       réglages de l'IA
//   #/privacy        confidentialité des données (en ligne)
//   #/welcome        premier lancement (…/setup, …/import, …/review/<id>, …/manual)

export type Route =
  | { view: 'cvs' }
  | { view: 'library' }
  | { view: 'settings' }
  | { view: 'privacy' }
  | { view: 'cv'; slug: string }
  | { view: 'target'; source?: string }
  | { view: 'welcome'; step: 'home' | 'setup' | 'import' | 'manual' }
  | { view: 'welcome'; step: 'review'; id: string }

function parse(hash: string): Route | null {
  const path = hash.replace(/^#\/?/, '')
  if (path === 'cvs' || path === 'library' || path === 'settings' || path === 'privacy') return { view: path }
  if (path === 'target') return { view: 'target' }
  if (path === 'welcome') return { view: 'welcome', step: 'home' }
  if (path === 'welcome/setup' || path === 'welcome/import' || path === 'welcome/manual')
    return { view: 'welcome', step: path.slice(8) as 'setup' | 'import' | 'manual' }
  const review = /^welcome\/review\/([0-9a-f]{12})$/.exec(path)
  if (review) return { view: 'welcome', step: 'review', id: review[1] }
  const cv = /^cv\/([a-z0-9-]+)$/.exec(path)
  if (cv) return { view: 'cv', slug: cv[1] }
  const target = /^target\/([a-z0-9-]+)$/.exec(path)
  return target ? { view: 'target', source: target[1] } : null
}

export function routeHash(route: Route): string {
  if (route.view === 'cv') return `#/cv/${route.slug}`
  if (route.view === 'target' && route.source) return `#/target/${route.source}`
  if (route.view === 'welcome') return route.step === 'review' ? `#/welcome/review/${route.id}` : route.step === 'home' ? '#/welcome' : `#/welcome/${route.step}`
  return `#/${route.view}`
}

export function useRoute(fallback: () => Route) {
  const [route, setRoute] = useState<Route>(() => parse(window.location.hash) ?? fallback())
  useEffect(() => {
    const onChange = () => {
      const next = parse(window.location.hash)
      if (next) setRoute(next)
    }
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  // L'adresse reflète toujours la page affichée.
  useEffect(() => {
    if (window.location.hash !== routeHash(route)) window.history.replaceState(null, '', routeHash(route))
  }, [route])
  const navigate = useCallback((next: Route) => {
    window.location.hash = routeHash(next)
  }, [])
  return { route, navigate }
}
