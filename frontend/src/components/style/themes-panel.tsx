import { Check, Loader2, RotateCcw, Save, Sparkle, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
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
import type { CvEditor } from '@/hooks/use-cv-editor'
import { api } from '@/lib/api'
import type { CVStyle, Theme } from '@/lib/types'
import { Group } from './controls'

interface ThemesPanelProps {
  style: CVStyle
  replaceStyle: CvEditor['replaceStyle']
}

/** Thèmes : enregistrer le style courant sous un nom, en appliquer un. */
export function ThemesPanel({ style, replaceStyle }: ThemesPanelProps) {
  const [themes, setThemes] = useState<Theme[] | null>(null)
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)
  const [toDelete, setToDelete] = useState<Theme | null>(null)

  const refresh = () =>
    api
      .listThemes()
      .then(setThemes)
      .catch(() => setThemes([]))
  useEffect(() => void refresh(), [])

  const save = async () => {
    if (!name.trim()) return
    setSaving(true)
    try {
      await api.createTheme(name.trim(), style)
      toast.success(`Thème « ${name.trim()} » enregistré`)
      setName('')
      await refresh()
    } catch (error) {
      toast.error("Le thème n'a pas été enregistré", { description: error instanceof Error ? error.message : String(error) })
    } finally {
      setSaving(false)
    }
  }

  const apply = (theme: Theme) => {
    replaceStyle(theme.style)
    toast.success(`Thème « ${theme.name} » appliqué`, { description: 'Ctrl+Z pour revenir en arrière.' })
  }

  const resetToBase = async () => {
    try {
      const base = await api.getCV('base')
      replaceStyle(base.style)
      toast.success('Style de la version classique appliqué', { description: 'Ctrl+Z pour revenir en arrière.' })
    } catch (error) {
      toast.error('Version classique indisponible', { description: error instanceof Error ? error.message : String(error) })
    }
  }

  const remove = async (theme: Theme) => {
    try {
      await api.deleteTheme(theme.slug)
      toast.success(`Thème « ${theme.name} » supprimé`)
      await refresh()
    } catch (error) {
      toast.error('Suppression impossible', { description: error instanceof Error ? error.message : String(error) })
    }
  }

  return (
    <Group title="Thèmes" hint="Enregistrer ce style, ou en appliquer un." icon={<Sparkle className="size-3.5" />}>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          void save()
        }}
      >
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Nom du thème, ex. Bleu sobre"
          maxLength={80}
          className="h-8 min-w-0 flex-1 rounded-md border bg-background px-2.5 text-[12.5px] shadow-xs outline-none focus:border-ring focus:ring-[3px] focus:ring-ring/40"
        />
        <Button type="submit" size="sm" className="h-8 gap-1.5 text-[12px]" disabled={!name.trim() || saving}>
          {saving ? <Loader2 className="size-3.5 animate-spin" /> : <Save className="size-3.5" />} Enregistrer
        </Button>
      </form>
      <div className="flex flex-col gap-1">
        {themes === null && <p className="text-[12px] text-muted-foreground">Chargement…</p>}
        {themes?.length === 0 && <p className="text-[12px] text-muted-foreground">Aucun thème enregistré pour l'instant.</p>}
        {themes?.map((theme) => (
          <div key={theme.slug} className="group/theme flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-muted/50">
            <span className="flex gap-0.5">
              {(['primary', 'band', 'accent'] as const).map((key) => (
                <span key={key} className="size-3 rounded-full border border-black/10" style={{ background: `#${theme.style.palette[key]}` }} />
              ))}
            </span>
            <span className="min-w-0 flex-1 truncate text-[12.5px]">{theme.name}</span>
            <Button variant="ghost" size="sm" className="h-7 gap-1 px-2 text-[12px]" onClick={() => apply(theme)}>
              <Check className="size-3.5" /> Appliquer
            </Button>
            <Button variant="ghost" size="icon" className="size-7 text-muted-foreground opacity-0 group-hover/theme:opacity-100 focus-visible:opacity-100" aria-label={`Supprimer le thème ${theme.name}`} onClick={() => setToDelete(theme)}>
              <Trash2 className="size-3.5" />
            </Button>
          </div>
        ))}
      </div>
      <Button variant="ghost" size="sm" className="h-7 self-start px-2 text-[12px] text-muted-foreground" onClick={() => void resetToBase()}>
        <RotateCcw className="size-3.5" /> Revenir au style de la version classique
      </Button>
      <AlertDialog open={toDelete !== null} onOpenChange={(open) => !open && setToDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Supprimer le thème « {toDelete?.name} » ?</AlertDialogTitle>
            <AlertDialogDescription>Les CV qui l'utilisent gardent leur style ; seul le thème enregistré disparaît.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Annuler</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={() => toDelete && void remove(toDelete)}>
              Supprimer
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Group>
  )
}
