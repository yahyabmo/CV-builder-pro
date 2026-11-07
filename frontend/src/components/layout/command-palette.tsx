import {
  BookMarked,
  Code2,
  Download,
  FileCode2,
  FileText,
  Mail,
  Monitor,
  Moon,
  Palette,
  Play,
  ScanSearch,
  Settings,
  Sheet,
  Sparkles,
  Sun,
  Target,
  Type,
} from 'lucide-react'
import { useEffect, useState } from 'react'

import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
  CommandShortcut,
} from '@/components/ui/command'
import type { Route } from '@/hooks/use-route'
import { useTheme } from '@/hooks/use-theme'
import { api } from '@/lib/api'
import type { CVSummary } from '@/lib/types'
import { PALETTE_EVENT, sendWorkspace, type Tab } from '@/lib/workspace-commands'

const TAB_ITEMS: { tab: Tab; label: string; icon: React.ReactNode }[] = [
  { tab: 'content', label: 'Contenu', icon: <Type /> },
  { tab: 'style', label: 'Style', icon: <Palette /> },
  { tab: 'offer', label: 'Offre visée', icon: <Target /> },
  { tab: 'letter', label: 'Lettre de motivation', icon: <Mail /> },
  { tab: 'latex', label: 'Code LaTeX', icon: <Code2 /> },
  { tab: 'ats', label: 'Vérification ATS', icon: <ScanSearch /> },
]

function download(href: string, name: string) {
  const link = document.createElement('a')
  link.href = href
  link.download = name
  link.click()
}

interface PaletteProps {
  cvs: CVSummary[] | null
  route: Route
  navigate: (route: Route) => void
}

/** Ctrl+K : aller n'importe où, ouvrir un CV, agir sur le CV ouvert. */
export function CommandPalette({ cvs, route, navigate }: PaletteProps) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const { setChoice } = useTheme()
  // Chaque ouverture repart d'une recherche vide.
  const show = (value: boolean | ((current: boolean) => boolean)) =>
    setOpen((current) => {
      const next = typeof value === 'function' ? value(current) : value
      if (next && !current) setSearch('')
      return next
    })

  useEffect(() => {
    // En phase de capture : l'éditeur de code ne doit pas avaler Ctrl+K.
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && !event.altKey && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        event.stopPropagation()
        show((current) => !current)
      }
    }
    const onOpen = () => show(true)
    window.addEventListener('keydown', onKey, true)
    window.addEventListener(PALETTE_EVENT, onOpen)
    return () => {
      window.removeEventListener('keydown', onKey, true)
      window.removeEventListener(PALETTE_EVENT, onOpen)
    }
  }, [])

  const run = (action: () => void) => () => {
    setOpen(false)
    action()
  }
  const current = route.view === 'cv' ? cvs?.find((cv) => cv.slug === route.slug) : undefined

  return (
    <CommandDialog open={open} onOpenChange={setOpen} title="Palette de commandes" description="Chercher une page, un CV ou une action">
      <Command>
      <CommandInput value={search} onValueChange={setSearch} placeholder="Chercher une page, un CV, une action…" />
      <CommandList>
        <CommandEmpty>Rien ne correspond.</CommandEmpty>

        {current && (
          <>
            <CommandGroup heading={`Ce CV : ${current.meta.name}`}>
              {TAB_ITEMS.map((item) => (
                <CommandItem key={item.tab} value={`onglet ${item.label}`} onSelect={run(() => sendWorkspace({ action: 'tab', tab: item.tab }))}>
                  {item.icon} {item.label}
                </CommandItem>
              ))}
              <CommandItem value="compiler maintenant" onSelect={run(() => sendWorkspace({ action: 'compile' }))}>
                <Play /> Compiler maintenant <CommandShortcut>Ctrl S</CommandShortcut>
              </CommandItem>
              <CommandItem value="cibler une offre à partir de ce cv" onSelect={run(() => navigate({ view: 'target', source: current.slug }))}>
                <Sparkles /> Cibler une offre à partir de ce CV
              </CommandItem>
              <CommandItem value="télécharger le pdf" disabled={!current.pdf_version} onSelect={run(() => download(api.pdfUrl(current.slug, current.pdf_version), `${current.file_stem}.pdf`))}>
                <Download /> Télécharger le PDF
              </CommandItem>
              <CommandItem value="télécharger le tex latex" onSelect={run(() => download(api.texUrl(current.slug), `${current.file_stem}.tex`))}>
                <FileCode2 /> Télécharger le .tex
              </CommandItem>
            </CommandGroup>
            <CommandSeparator />
          </>
        )}

        <CommandGroup heading="Aller à">
          <CommandItem value="candidatures mes cv suivi relances" onSelect={run(() => navigate({ view: 'cvs' }))}>
            <Sheet /> Candidatures
          </CommandItem>
          <CommandItem value="cibler une offre" onSelect={run(() => navigate({ view: 'target' }))}>
            <Sparkles /> Cibler une offre
          </CommandItem>
          <CommandItem value="bibliothèque compétences projets expériences" onSelect={run(() => navigate({ view: 'library' }))}>
            <BookMarked /> Bibliothèque
          </CommandItem>
          <CommandItem value="réglages ia gemini mistral ollama" onSelect={run(() => navigate({ view: 'settings' }))}>
            <Settings /> Réglages
          </CommandItem>
        </CommandGroup>

        {cvs && cvs.length > 0 && (
          <>
            <CommandSeparator />
            <CommandGroup heading="Ouvrir un CV">
              {cvs.map((cv) => (
                <CommandItem
                  key={cv.slug}
                  value={`cv ${cv.meta.name} ${cv.meta.company ?? ''} ${cv.meta.position ?? ''} ${cv.slug}`}
                  onSelect={run(() => navigate({ view: 'cv', slug: cv.slug }))}
                >
                  <FileText /> {cv.meta.name}
                  {cv.meta.score != null && <CommandShortcut>{cv.meta.score} %</CommandShortcut>}
                </CommandItem>
              ))}
            </CommandGroup>
          </>
        )}

        <CommandSeparator />
        <CommandGroup heading="Thème">
          <CommandItem value="thème clair" onSelect={run(() => setChoice('light'))}>
            <Sun /> Clair
          </CommandItem>
          <CommandItem value="thème sombre" onSelect={run(() => setChoice('dark'))}>
            <Moon /> Sombre
          </CommandItem>
          <CommandItem value="thème système" onSelect={run(() => setChoice('system'))}>
            <Monitor /> Système
          </CommandItem>
        </CommandGroup>
      </CommandList>
      </Command>
    </CommandDialog>
  )
}
