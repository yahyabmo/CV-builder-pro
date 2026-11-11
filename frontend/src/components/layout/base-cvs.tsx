import { Copy, MoreHorizontal, PencilLine, Plus, Trash2, Upload } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { Route } from '@/hooks/use-route'
import { dayLabel } from '@/lib/applications'
import { api } from '@/lib/api'
import { baseCVs } from '@/lib/bases'
import type { CVSummary } from '@/lib/types'
import { cn } from '@/lib/utils'
import { clearIntent, setIntent } from '@/lib/welcome-intent'

interface BaseCVsProps {
  cvs: CVSummary[] | null
  route: Route
  navigate: (route: Route) => void
  refresh: () => Promise<void>
  collapsed: boolean
}

/** « Mes CV classiques » dans la barre de gauche : la liste, « + Ajouter », et le menu de chacun. */
export function BaseCVs({ cvs, route, navigate, refresh, collapsed }: BaseCVsProps) {
  const [renaming, setRenaming] = useState<{ cv: CVSummary; name: string } | null>(null)
  const [deleting, setDeleting] = useState<CVSummary | null>(null)
  const bases = cvs ? baseCVs(cvs) : []
  const open = (slug: string) => route.view === 'cv' && route.slug === slug

  const add = () => {
    clearIntent()
    navigate({ view: 'welcome', step: 'new' })
  }
  const replace = (cv: CVSummary) => {
    setIntent({ mode: 'replace', target: cv.slug, name: cv.meta.name })
    navigate({ view: 'welcome', step: 'home' })
  }
  const duplicate = async (cv: CVSummary) => {
    try {
      const copy = await api.createCV(`${cv.meta.name} (copie)`, cv.slug, 'base')
      await refresh()
      toast.success(`« ${copy.meta.name} » ajouté à tes CV classiques`)
      navigate({ view: 'cv', slug: copy.slug })
    } catch (error) {
      toast.error('Copie impossible', { description: (error as Error).message })
    }
  }
  const rename = async () => {
    if (!renaming || !renaming.name.trim()) return
    try {
      await api.renameCV(renaming.cv.slug, renaming.name.trim())
      await refresh()
      setRenaming(null)
    } catch (error) {
      toast.error('Renommage impossible', { description: (error as Error).message })
    }
  }
  const remove = async (cv: CVSummary) => {
    try {
      await api.deleteCV(cv.slug)
      await refresh()
      toast.success(`« ${cv.meta.name} » mis à la corbeille`)
      // La première version supprimée : un autre CV classique a pris sa place sous « base ».
      if (open(cv.slug) && cv.slug !== 'base') navigate({ view: 'cv', slug: 'base' })
    } catch (error) {
      toast.error('Suppression impossible', { description: (error as Error).message })
    }
  }

  const menu = (cv: CVSummary, className?: string) => (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={`Menu de ${cv.meta.name}`}
          className={cn('flex size-6 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-foreground', className)}
        >
          <MoreHorizontal className="size-4" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="right" className="w-56">
        <DropdownMenuItem onSelect={() => setRenaming({ cv, name: cv.meta.name })}>
          <PencilLine className="size-3.5" /> Renommer
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => void duplicate(cv)}>
          <Copy className="size-3.5" /> Dupliquer
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => replace(cv)}>
          <Upload className="size-3.5" /> Remplacer par un autre…
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem variant="destructive" disabled={bases.length < 2} onSelect={() => setDeleting(cv)}>
          <Trash2 className="size-3.5" /> {bases.length < 2 ? 'Supprimer (le seul qui reste)' : 'Supprimer'}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )

  const dialogs = (
    <>
      <Dialog open={renaming !== null} onOpenChange={(next) => !next && setRenaming(null)}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Renommer ce CV classique</DialogTitle>
            <DialogDescription>Le nom sert dans la liste et dans « Cibler une offre ».</DialogDescription>
          </DialogHeader>
          <form
            onSubmit={(e) => {
              e.preventDefault()
              void rename()
            }}
          >
            <Input autoFocus value={renaming?.name ?? ''} maxLength={120} aria-label="Nom du CV classique" onChange={(e) => renaming && setRenaming({ ...renaming, name: e.target.value })} />
            <DialogFooter className="pt-4">
              <Button type="submit" disabled={!renaming?.name.trim()}>
                Renommer
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
      <AlertDialog open={deleting !== null} onOpenChange={(next) => !next && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Mettre « {deleting?.meta.name} » à la corbeille ?</AlertDialogTitle>
            <AlertDialogDescription>
              Tes autres CV classiques et tes candidatures ne bougent pas. Il reste récupérable dans la corbeille.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Garder</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => {
                if (deleting) void remove(deleting)
              }}
            >
              Mettre à la corbeille
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )

  if (collapsed) {
    return (
      <div className="flex flex-col items-center gap-1.5 pt-5">
        {bases.map((cv) => (
          <Tooltip key={cv.slug}>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={() => navigate({ view: 'cv', slug: cv.slug })}
                aria-label={cv.meta.name}
                aria-current={open(cv.slug) ? 'page' : undefined}
                className={cn('rounded-md p-1 transition-colors hover:bg-sidebar-accent', open(cv.slug) && 'bg-sidebar-accent shadow-xs')}
              >
                <Thumbnail cv={cv} />
              </button>
            </TooltipTrigger>
            <TooltipContent side="right">{cv.meta.name}</TooltipContent>
          </Tooltip>
        ))}
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={add}
              aria-label="Ajouter un CV classique"
              className="flex size-8 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-foreground"
            >
              <Plus className="size-4" />
            </button>
          </TooltipTrigger>
          <TooltipContent side="right">Ajouter un CV classique</TooltipContent>
        </Tooltip>
        {dialogs}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-1.5 px-2.5 pt-6">
      <div className="flex items-center justify-between px-2">
        <p className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">Mes CV classiques</p>
        <button
          type="button"
          onClick={add}
          className="flex items-center gap-0.5 rounded px-1 text-[11.5px] font-medium text-primary transition-colors hover:text-foreground"
        >
          <Plus className="size-3" /> Ajouter
        </button>
      </div>
      {cvs === null && <div className="h-14 animate-pulse rounded-lg bg-sidebar-accent/60" />}
      {bases.map((cv) => (
        <div
          key={cv.slug}
          className={cn(
            'group flex items-center gap-1 rounded-xl border bg-background/70 pr-1 transition-colors hover:bg-background',
            open(cv.slug) && 'border-primary/40 bg-background ring-1 ring-primary/20',
          )}
        >
          <button
            type="button"
            onClick={() => navigate({ view: 'cv', slug: cv.slug })}
            aria-current={open(cv.slug) ? 'page' : undefined}
            className="flex min-w-0 flex-1 items-center gap-2.5 p-2 text-left"
          >
            <Thumbnail cv={cv} />
            <span className="flex min-w-0 flex-col">
              <span className="truncate text-[13px] font-medium">{cv.meta.name}</span>
              <span className="truncate text-[11.5px] text-muted-foreground">
                {cv.meta.pages != null && `${cv.meta.pages} p. · `}modifié le {dayLabel(cv.meta.updated_at)}
              </span>
            </span>
          </button>
          {menu(cv)}
        </div>
      ))}
      {dialogs}
    </div>
  )
}

function Thumbnail({ cv }: { cv: CVSummary }) {
  return cv.pdf_version ? (
    <img src={api.thumbnailUrl(cv.slug, cv.pdf_version)} alt="" className="h-11 w-8 shrink-0 rounded-sm border bg-white object-cover object-top" />
  ) : (
    <span className="block h-11 w-8 shrink-0 rounded-sm border bg-muted" />
  )
}
