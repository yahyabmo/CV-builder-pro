import { useCallback, useEffect, useState } from 'react'
import { toast } from 'sonner'

import { AdminPage } from '@/components/admin/admin-page'
import { AccessPaused } from '@/components/layout/access-paused'
import { ApplicationsPage } from '@/components/cvs/applications-page'
import { CommandPalette } from '@/components/layout/command-palette'
import { Sidebar } from '@/components/layout/sidebar'
import { Workspace } from '@/components/layout/workspace'
import { LibraryPage } from '@/components/library/library-page'
import { PrivacyPage } from '@/components/settings/privacy-page'
import { SettingsPage } from '@/components/settings/settings-page'
import { TargetPage } from '@/components/target/target-page'
import { WelcomeFlow } from '@/components/welcome/welcome-flow'
import { useRoute, type Route } from '@/hooks/use-route'
import { ACCESS_PAUSED, api } from '@/lib/api'
import type { CVSummary } from '@/lib/types'

const LAST = 'cv-builder.selected'
const FOLDED = 'cv-builder.sidebar.collapsed'

function readFolded(): boolean {
  try {
    return localStorage.getItem(FOLDED) === '1'
  } catch {
    return false
  }
}

// Au premier lancement (pas d'adresse) : le dernier CV ouvert, sinon la base.
function initialRoute(): Route {
  try {
    const last = localStorage.getItem(LAST)
    if (last) return { view: 'cv', slug: last }
  } catch {
    /* stockage indisponible */
  }
  return { view: 'cv', slug: 'base' }
}

export default function App() {
  const [cvs, setCvs] = useState<CVSummary[] | null>(null)
  const { route, navigate } = useRoute(initialRoute)
  const [collapsed, setCollapsed] = useState(readFolded)
  // En ligne : l'accès de cette adresse a été retiré (son e-mail), l'appli laisse place à un écran.
  const [paused, setPaused] = useState<string | null>(null)
  useEffect(() => {
    const onPaused = (event: Event) => setPaused((event as CustomEvent<string>).detail)
    window.addEventListener(ACCESS_PAUSED, onPaused)
    return () => window.removeEventListener(ACCESS_PAUSED, onPaused)
  }, [])
  const toggleSidebar = () =>
    setCollapsed((current) => {
      try {
        localStorage.setItem(FOLDED, current ? '0' : '1')
      } catch {
        /* le choix vaut pour cette session */
      }
      return !current
    })

  const refresh = useCallback(
    () =>
      api
        .listCVs()
        .then(setCvs)
        .catch((error: Error) => {
          setCvs([])
          toast.error('Liste des CV indisponible', { description: error.message })
        }),
    [],
  )

  useEffect(() => {
    void refresh()
    // La liste montre la date de modification : on la rafraîchit de temps en temps.
    const timer = window.setInterval(() => void refresh(), 30_000)
    return () => window.clearInterval(timer)
  }, [refresh])

  // Un CV ouvert qui n'existe plus (supprimé) : retour à la liste.
  useEffect(() => {
    if (route.view === 'cv' && cvs && !cvs.some((cv) => cv.slug === route.slug)) navigate({ view: 'cvs' })
  }, [route, cvs, navigate])

  useEffect(() => {
    if (route.view !== 'cv') return
    try {
      localStorage.setItem(LAST, route.slug)
    } catch {
      /* le choix vaut pour cette session */
    }
  }, [route])

  // Au démarrage, tant que la version classique est le CV fictif : l'accueil, précédé
  // de l'écran de démarrage (modèle d'IA, machine) s'il n'a pas encore été passé.
  useEffect(() => {
    api.welcome().then(({ show, setup }) => {
      const hash = window.location.hash
      if (!show) return
      if (setup && (hash === '#/welcome' || !hash.startsWith('#/welcome'))) navigate({ view: 'welcome', step: 'setup' })
      else if (!hash.startsWith('#/welcome')) navigate({ view: 'welcome', step: 'home' })
    }, () => undefined)
  }, [navigate])

  const openCV = (slug: string) => navigate({ view: 'cv', slug })

  if (paused !== null) return <AccessPaused email={paused} />
  if (route.view === 'welcome') return <WelcomeFlow route={route} navigate={navigate} refresh={refresh} />

  return (
    <div className="flex h-dvh overflow-hidden">
      <Sidebar cvs={cvs} route={route} navigate={navigate} collapsed={collapsed} onToggle={toggleSidebar} />
      <main className="h-full min-w-0 flex-1">
          {route.view === 'cvs' && (
            <ApplicationsPage cvs={cvs} onOpen={openCV} onTarget={() => navigate({ view: 'target' })} refresh={refresh} />
          )}
          {route.view === 'library' && <LibraryPage />}
          {route.view === 'settings' && <SettingsPage />}
          {route.view === 'privacy' && <PrivacyPage />}
          {route.view === 'admin' && <AdminPage email={route.email} navigate={navigate} />}
          {route.view === 'target' && (
            <TargetPage key={route.source ?? ''} cvs={cvs} source={route.source} navigate={navigate} refresh={refresh} />
          )}
          {route.view === 'cv' && <Workspace key={route.slug} slug={route.slug} />}
      </main>
      <CommandPalette cvs={cvs} route={route} navigate={navigate} />
    </div>
  )
}
