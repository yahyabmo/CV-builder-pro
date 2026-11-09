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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useMe } from '@/hooks/use-me'
import { api } from '@/lib/api'
import { shortLabel } from '@/lib/format'
import type { CVSummary } from '@/lib/types'

export function NewCVDialog({ state, cvs, onClose, onCreated }: { state: { source: string; name: string } | null; cvs: CVSummary[]; onClose: () => void; onCreated: (slug: string) => Promise<void> }) {
  const [name, setName] = useState('')
  const [source, setSource] = useState('base')
  const [busy, setBusy] = useState(false)
  const [opened, setOpened] = useState<typeof state>(null)
  // Préremplissage à chaque ouverture (nouveau CV, ou duplication d'un CV).
  if (state !== opened) {
    setOpened(state)
    if (state) {
      setName(state.name)
      setSource(state.source)
    }
  }
  const create = async () => {
    if (!name.trim()) return
    setBusy(true)
    try {
      const created = await api.createCV(name.trim(), source)
      toast.success(`« ${created.meta.name} » créé`)
      await onCreated(created.slug)
    } catch (error) {
      toast.error('Création impossible', { description: error instanceof Error ? error.message : String(error) })
    } finally {
      setBusy(false)
    }
  }
  return (
    <Dialog open={state !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Nouveau CV</DialogTitle>
          <DialogDescription>Une copie d'un CV existant, que tu adaptes ensuite.</DialogDescription>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); void create() }}>
          <label className="flex flex-col gap-1.5">
            <span className="text-[12px] font-medium">Nom</span>
            <input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="ex. Thales — Ingénieur IA" maxLength={120} className="h-9 rounded-md border bg-background px-3 text-[13px] shadow-xs outline-none focus:border-ring focus:ring-[3px] focus:ring-ring/40" />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-[12px] font-medium">À partir de</span>
            <Select value={source} onValueChange={setSource}>
              <SelectTrigger className="h-9 text-[13px]"><SelectValue /></SelectTrigger>
              <SelectContent>
                {cvs.map((cv) => <SelectItem key={cv.slug} value={cv.slug} className="text-[13px]">{cv.meta.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </label>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>Annuler</Button>
            <Button type="submit" disabled={busy || !name.trim()}>{busy ? 'Création…' : 'Créer'}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function RenameDialog({ cv, onClose, onDone }: { cv: CVSummary | null; onClose: () => void; onDone: () => Promise<void> }) {
  const [name, setName] = useState('')
  const [label, setLabel] = useState('')
  const [opened, setOpened] = useState<CVSummary | null>(null)
  if (cv !== opened) {
    setOpened(cv)
    if (cv) {
      setName(cv.meta.name)
      setLabel(cv.file_label)
    }
  }
  // « camille_laurent » : le nom du fichier sans les mots de l'offre.
  const person = cv ? (cv.file_label ? cv.file_stem.slice(0, -(cv.file_label.length + 1)) : cv.file_stem) : ''
  const words = shortLabel(label)
  const save = async () => {
    if (!cv || !name.trim()) return
    try {
      const saved = await api.renameCV(cv.slug, name.trim(), label === cv.file_label ? undefined : label)
      toast.success('CV renommé', { description: `Fichier : ${saved.file_stem}.pdf` })
      await onDone()
    } catch (error) {
      toast.error('Renommage impossible', { description: error instanceof Error ? error.message : String(error) })
    }
  }
  return (
    <Dialog open={cv !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Renommer le CV</DialogTitle>
          <DialogDescription>Le nom affiché dans tes listes ; le dossier du CV ne change pas.</DialogDescription>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); void save() }}>
          <input autoFocus value={name} onChange={(e) => setName(e.target.value)} maxLength={120} aria-label="Nom du CV" className="h-9 rounded-md border bg-background px-3 text-[13px] shadow-xs outline-none focus:border-ring focus:ring-[3px] focus:ring-ring/40" />
          <label className="flex flex-col gap-1.5">
            <span className="text-[12px] text-muted-foreground">L'offre en 1 à 3 mots, pour le nom du fichier téléchargé</span>
            <input value={label} onChange={(e) => setLabel(e.target.value)} maxLength={60} placeholder="ex. agent SRE" aria-label="Mots de l'offre" className="h-9 rounded-md border bg-background px-3 text-[13px] shadow-xs outline-none focus:border-ring focus:ring-[3px] focus:ring-ring/40" />
            <span className="font-mono text-[11.5px] text-muted-foreground">
              {person}
              {words ? `_${words}` : ''}.pdf
            </span>
          </label>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>Annuler</Button>
            <Button type="submit" disabled={!name.trim()}>Renommer</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function DeleteDialog({ cv, onClose, onDone }: { cv: CVSummary | null; onClose: () => void; onDone: () => Promise<void> }) {
  const me = useMe()
  const remove = async () => {
    if (!cv) return
    try {
      await api.deleteCV(cv.slug)
      toast.success(`« ${cv.meta.name} » mis à la corbeille`)
      await onDone()
    } catch (error) {
      toast.error('Suppression impossible', { description: error instanceof Error ? error.message : String(error) })
    }
  }
  return (
    <AlertDialog open={cv !== null} onOpenChange={(open) => !open && onClose()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Supprimer « {cv?.meta.name} » ?</AlertDialogTitle>
          <AlertDialogDescription>
            {me?.mode === 'serveur' ? (
              <>Le CV, sa lettre et le suivi de la candidature disparaissent de l'application. Pour en récupérer un, demande à Yahya.</>
            ) : (
              <>
                Le CV, sa lettre et le suivi de la candidature partent dans <code>data/corbeille/</code> : ils disparaissent de
                l'application, mais restent récupérables à la main.
              </>
            )}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Annuler</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={() => void remove()}>
            Supprimer
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
