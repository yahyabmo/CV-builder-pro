import { BookMarked, Monitor, Moon, PanelLeftClose, PanelLeftOpen, Search, Settings, Sheet, ShieldCheck, Sparkles, Sun } from 'lucide-react'

import { ScrollArea } from '@/components/ui/scroll-area'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useMe } from '@/hooks/use-me'
import type { Route } from '@/hooks/use-route'
import { useTheme, type ThemeChoice } from '@/hooks/use-theme'
import { dayLabel } from '@/lib/applications'
import { api } from '@/lib/api'
import type { CVSummary } from '@/lib/types'
import { cn } from '@/lib/utils'
import { openPalette } from '@/lib/workspace-commands'

import { Account } from './account'

interface SidebarProps {
  cvs: CVSummary[] | null
  route: Route
  navigate: (route: Route) => void
  // Replié : seulement les icônes, pour laisser la place à l'éditeur.
  collapsed: boolean
  onToggle: () => void
}

export function Sidebar({ cvs, route, navigate, collapsed, onToggle }: SidebarProps) {
  const me = useMe()
  const base = cvs?.find((cv) => cv.meta.kind === 'base') ?? null
  const due = cvs?.filter((cv) => cv.due).length ?? 0
  const onBase = route.view === 'cv' && base !== null && route.slug === base.slug
  const items = [
    { label: 'Candidatures', icon: <Sheet className="size-4" />, active: route.view === 'cvs', go: () => navigate({ view: 'cvs' }), badge: due },
    { label: 'Cibler une offre', icon: <Sparkles className="size-4" />, active: route.view === 'target', go: () => navigate({ view: 'target' }), badge: 0 },
    { label: 'Bibliothèque', icon: <BookMarked className="size-4" />, active: route.view === 'library', go: () => navigate({ view: 'library' }), badge: 0 },
    { label: 'Réglages', icon: <Settings className="size-4" />, active: route.view === 'settings', go: () => navigate({ view: 'settings' }), badge: 0 },
    // En ligne, pour l'administrateur seulement.
    ...(me?.admin
      ? [{ label: 'Administration', icon: <ShieldCheck className="size-4" />, active: route.view === 'admin', go: () => navigate({ view: 'admin' }), badge: 0 }]
      : []),
  ]

  return (
    <aside
      aria-label="Menu"
      className={cn(
        'sidebar-scope flex h-full shrink-0 flex-col border-r bg-sidebar text-sidebar-foreground transition-[width] duration-200',
        collapsed ? 'w-14' : 'w-[232px]',
      )}
    >
      <div className={cn('flex h-12 shrink-0 items-center gap-2.5', collapsed ? 'justify-center' : 'pr-2 pl-4')}>
        <img src="/favicon.png" alt="" className="size-7 shrink-0" />
        {!collapsed && (
          <>
            <span className="min-w-0 flex-1 truncate text-[14px] font-semibold tracking-tight">CV Builder Pro</span>
            <FoldButton collapsed={collapsed} onToggle={onToggle} />
          </>
        )}
      </div>

      <div className={cn('pt-1', collapsed ? 'flex justify-center' : 'px-2.5')}>
        {collapsed ? (
          <Hint label="Rechercher (Ctrl K)">
            <button
              type="button"
              onClick={openPalette}
              aria-label="Rechercher"
              className="flex size-9 items-center justify-center rounded-lg text-sidebar-foreground/80 transition-colors hover:bg-sidebar-accent hover:text-foreground"
            >
              <Search className="size-4" />
            </button>
          </Hint>
        ) : (
          <button
            type="button"
            onClick={openPalette}
            className="flex w-full items-center gap-2 rounded-lg border bg-background/70 px-2.5 py-1.5 text-[12.5px] text-muted-foreground shadow-xs transition-colors hover:bg-background hover:text-foreground"
          >
            <Search className="size-3.5" />
            Rechercher…
            <kbd className="ml-auto font-mono text-[10.5px]">Ctrl K</kbd>
          </button>
        )}
      </div>

      <ScrollArea className="min-h-0 flex-1">
        <nav className={cn('flex flex-col gap-0.5 pt-3', collapsed ? 'items-center' : 'px-2.5')}>
          {items.map((item) => (
            <NavItem key={item.label} {...item} collapsed={collapsed} />
          ))}
        </nav>

        {collapsed ? (
          base && (
            <div className="flex justify-center pt-5">
              <Hint label="Ton CV de base">
                <button
                  type="button"
                  onClick={() => navigate({ view: 'cv', slug: base.slug })}
                  aria-label="Ton CV de base"
                  aria-current={onBase ? 'page' : undefined}
                  className={cn('rounded-md p-1 transition-colors hover:bg-sidebar-accent', onBase && 'bg-sidebar-accent shadow-xs')}
                >
                  <Thumbnail cv={base} />
                </button>
              </Hint>
            </div>
          )
        ) : (
          <div className="flex flex-col gap-1.5 px-2.5 pt-6">
            <div className="flex items-center justify-between px-2">
              <p className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">Ton CV de base</p>
              <button
                type="button"
                onClick={() => navigate({ view: 'welcome', step: 'home' })}
                className="rounded px-1 text-[11.5px] text-muted-foreground transition-colors hover:text-foreground"
              >
                Remplacer
              </button>
            </div>
            {cvs === null && <div className="h-14 animate-pulse rounded-lg bg-sidebar-accent/60" />}
            {base && (
              <button
                type="button"
                onClick={() => navigate({ view: 'cv', slug: base.slug })}
                aria-current={onBase ? 'page' : undefined}
                className={cn(
                  'flex items-center gap-2.5 rounded-xl border bg-background/70 p-2 text-left transition-colors hover:bg-background',
                  onBase && 'border-primary/40 bg-background ring-1 ring-primary/20',
                )}
              >
                <Thumbnail cv={base} />
                <span className="flex min-w-0 flex-col">
                  <span className="truncate text-[13px] font-medium">{base.meta.name}</span>
                  <span className="truncate text-[11.5px] text-muted-foreground">
                    {base.meta.pages != null && `${base.meta.pages} p. · `}modifiée le {dayLabel(base.meta.updated_at)}
                  </span>
                </span>
              </button>
            )}
          </div>
        )}
      </ScrollArea>

      {me?.mode === 'serveur' && me.email && (
        <div className={cn('flex shrink-0 border-t p-2', collapsed && 'justify-center')}>
          <Account
            email={me.email}
            collapsed={collapsed}
            refreshKey={JSON.stringify(route)}
            openPrivacy={() => navigate({ view: 'privacy' })}
          />
        </div>
      )}

      <div className={cn('flex shrink-0 gap-1 border-t p-2', collapsed ? 'flex-col items-center' : 'items-center')}>
        <ThemeSwitch collapsed={collapsed} />
        {collapsed && <FoldButton collapsed={collapsed} onToggle={onToggle} />}
      </div>
    </aside>
  )
}

/** Replier le menu (en haut, à côté du nom) ou le déplier (en bas des icônes). */
function FoldButton({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const label = collapsed ? 'Déplier le menu' : 'Replier le menu'
  return (
    <Hint label={label}>
      <button
        type="button"
        onClick={onToggle}
        aria-label={label}
        aria-expanded={!collapsed}
        className="flex size-8 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-foreground"
      >
        {collapsed ? <PanelLeftOpen className="size-4" /> : <PanelLeftClose className="size-4" />}
      </button>
    </Hint>
  )
}

/** Une info-bulle, à droite du menu. */
function Hint({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent side="right">{label}</TooltipContent>
    </Tooltip>
  )
}

function Thumbnail({ cv }: { cv: CVSummary }) {
  return cv.pdf_version ? (
    <img src={api.thumbnailUrl(cv.slug, cv.pdf_version)} alt="" className="h-11 w-8 shrink-0 rounded-sm border bg-white object-cover object-top" />
  ) : (
    <span className="block h-11 w-8 shrink-0 rounded-sm border bg-muted" />
  )
}

interface NavItemProps {
  label: string
  icon: React.ReactNode
  active: boolean
  go: () => void
  badge: number
  collapsed: boolean
}

function NavItem({ label, icon, active, go, badge, collapsed }: NavItemProps) {
  const due = badge > 0 ? `${badge} relance${badge > 1 ? 's' : ''} à faire` : undefined
  const look = active ? 'bg-sidebar-accent font-medium text-sidebar-accent-foreground shadow-xs' : 'text-sidebar-foreground/90 hover:bg-sidebar-accent/70'
  if (collapsed) {
    return (
      <Hint label={due ? `${label} · ${due}` : label}>
        <button
          type="button"
          onClick={go}
          aria-label={label}
          aria-current={active ? 'page' : undefined}
          className={cn('relative flex size-9 items-center justify-center rounded-lg transition-colors', look)}
        >
          {icon}
          {badge > 0 && (
            <span
              aria-label={due}
              className="absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-status-interview-soft px-1 font-mono text-[9.5px] font-semibold text-status-interview ring-2 ring-sidebar"
            >
              {badge}
            </span>
          )}
        </button>
      </Hint>
    )
  }
  return (
    <button
      type="button"
      onClick={go}
      aria-current={active ? 'page' : undefined}
      className={cn('flex h-9 items-center gap-2.5 rounded-lg px-2.5 text-[13.5px] transition-colors', look)}
    >
      {icon}
      {label}
      {badge > 0 && (
        <span
          aria-label={due}
          className="ml-auto flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-status-interview-soft px-1.5 font-mono text-[10.5px] font-semibold text-status-interview"
        >
          {badge}
        </span>
      )}
    </button>
  )
}

const THEMES: { value: ThemeChoice; label: string; icon: React.ReactNode }[] = [
  { value: 'light', label: 'Clair', icon: <Sun className="size-3.5" /> },
  { value: 'dark', label: 'Sombre', icon: <Moon className="size-3.5" /> },
  { value: 'system', label: 'Système', icon: <Monitor className="size-3.5" /> },
]

function ThemeSwitch({ collapsed }: { collapsed: boolean }) {
  const { choice, setChoice } = useTheme()
  if (collapsed) {
    // Replié : un seul bouton, qui passe au thème suivant.
    const index = Math.max(0, THEMES.findIndex((theme) => theme.value === choice))
    const current = THEMES[index]
    const next = THEMES[(index + 1) % THEMES.length]
    return (
      <Hint label={`Thème ${current.label.toLowerCase()} : passer au thème ${next.label.toLowerCase()}`}>
        <button
          type="button"
          onClick={() => setChoice(next.value)}
          aria-label={`Thème : ${current.label}`}
          className="flex size-8 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-foreground"
        >
          {current.icon}
        </button>
      </Hint>
    )
  }
  return (
    <div role="radiogroup" aria-label="Thème" className="grid flex-1 grid-cols-3 gap-0.5 rounded-lg bg-border/60 p-0.5">
      {THEMES.map((theme) => (
        <button
          key={theme.value}
          type="button"
          role="radio"
          aria-checked={choice === theme.value}
          onClick={() => setChoice(theme.value)}
          className={cn(
            'flex items-center justify-center gap-1 rounded-md py-1 text-[11px] transition-colors',
            choice === theme.value ? 'bg-card text-foreground shadow-xs' : 'text-muted-foreground hover:text-foreground',
          )}
        >
          {theme.icon}
          {theme.label}
        </button>
      ))}
    </div>
  )
}
