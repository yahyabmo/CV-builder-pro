import { Check, Loader2, Upload } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import { Segmented } from '@/components/style/controls'
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
import type { LetterEditor } from '@/hooks/use-letter-editor'
import { api } from '@/lib/api'
import type { SignatureInfo, SignatureSize } from '@/lib/types'
import { cn } from '@/lib/utils'

const SIZES: { value: SignatureSize; label: string; title: string }[] = [
  { value: 'small', label: 'Petite', title: '1,2 cm de haut' },
  { value: 'medium', label: 'Moyenne', title: '1,6 cm de haut' },
  { value: 'large', label: 'Grande', title: '2 cm de haut' },
]
const ACCEPT = 'image/png,image/jpeg,image/webp'
// Damier : la transparence de l'image se voit.
const CHECKER =
  'repeating-conic-gradient(#eceef4 0% 25%, #ffffff 0% 50%) 50% / 12px 12px'

/** Sous le nom : l'image de signature, la même pour toutes les lettres, et sa case pour celle-ci. */
export function SignatureImage({ editor }: { editor: LetterEditor }) {
  const [info, setInfo] = useState<SignatureInfo | null>(null)
  const [busy, setBusy] = useState(false)
  const [over, setOver] = useState(false)
  const [removing, setRemoving] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const letter = editor.letter
  const on = letter?.signature_image !== false

  useEffect(() => {
    api.signature().then(setInfo, () => setInfo({ present: false, size: 'medium', version: null }))
  }, [])

  // Une image changée vaut pour toutes les lettres : celle-ci se recompile tout de suite.
  const apply = (next: SignatureInfo, message: string, description?: string) => {
    setInfo(next)
    editor.recompile()
    toast.success(message, description ? { description } : undefined)
  }

  const upload = async (file: File | undefined) => {
    if (!file) return
    setBusy(true)
    try {
      apply(await api.uploadSignature(file, file.name), 'Signature ajoutée', 'Fond retiré et image recadrée au trait. Elle sert à toutes tes lettres.')
    } catch (error) {
      toast.error('Image refusée', { description: (error as Error).message })
    } finally {
      setBusy(false)
      if (input.current) input.current.value = ''
    }
  }

  const run = async (call: () => Promise<SignatureInfo>, message: string) => {
    try {
      apply(await call(), message)
    } catch (error) {
      toast.error('Impossible', { description: (error as Error).message })
    }
  }

  if (info === null || letter === null) return null

  const picker = (
    <input ref={input} type="file" accept={ACCEPT} className="hidden" aria-label="Image de signature" onChange={(e) => void upload(e.target.files?.[0])} />
  )

  if (!info.present) {
    return (
      <div className="flex flex-col gap-1.5">
        <span className="text-[12.5px] font-medium">Image de signature</span>
        {picker}
        <button
          type="button"
          disabled={busy || editor.manual}
          onClick={() => input.current?.click()}
          onDragOver={(e) => {
            e.preventDefault()
            setOver(true)
          }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => {
            e.preventDefault()
            setOver(false)
            void upload(e.dataTransfer.files[0])
          }}
          className={cn(
            'flex items-center gap-3 rounded-lg border-[1.5px] border-dashed bg-background px-3 py-3 text-left text-[12.5px] text-muted-foreground transition-colors hover:bg-accent',
            over && 'border-primary bg-accent',
          )}
        >
          {busy ? <Loader2 className="size-4 shrink-0 animate-spin" /> : <Upload className="size-4 shrink-0" />}
          <span>
            <span className="font-medium text-foreground">Dépose l'image de ta signature</span>, ou clique pour la choisir. PNG, JPEG ou WebP,
            5 Mo au plus. Une photo sur papier blanc convient : le fond est retiré.
          </span>
        </button>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[12.5px] font-medium">Image de signature</span>
      {picker}
      <div className="flex flex-col gap-3 rounded-lg border bg-muted/40 p-3">
        <div className="flex flex-wrap items-center gap-3">
          <span className="flex h-16 w-40 items-center justify-center overflow-hidden rounded-md border" style={{ background: CHECKER }}>
            <img src={api.signatureImageUrl(info.version)} alt="Ta signature" className="max-h-14 max-w-36 object-contain" />
          </span>
          <span className="flex flex-col text-[12px] text-muted-foreground">
            <span>Fond retiré, recadrée au trait.</span>
            <span>Sert à toutes tes lettres.</span>
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[12px] text-muted-foreground">Taille</span>
          <Segmented value={info.size} options={SIZES} onChange={(size) => void run(() => api.setSignatureSize(size), 'Taille de la signature changée')} />
        </div>
        <button
          type="button"
          role="checkbox"
          aria-checked={on}
          disabled={editor.manual}
          onClick={() => editor.update((draft) => void (draft.signature_image = !on))}
          className="flex items-center gap-2 self-start text-[12.5px]"
        >
          <span className={cn('flex size-4 items-center justify-center rounded border', on ? 'border-primary bg-primary text-primary-foreground' : 'bg-background')}>
            {on && <Check className="size-3" strokeWidth={3} />}
          </span>
          La mettre sur cette lettre
        </button>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" className="h-8 gap-1.5" disabled={busy || editor.manual} onClick={() => input.current?.click()}>
            {busy ? <Loader2 className="size-3.5 animate-spin" /> : <Upload className="size-3.5" />} Remplacer
          </Button>
          <Button variant="ghost" size="sm" className="h-8 text-muted-foreground" disabled={editor.manual} onClick={() => setRemoving(true)}>
            Retirer
          </Button>
        </div>
      </div>
      <AlertDialog open={removing} onOpenChange={setRemoving}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Retirer ta signature ?</AlertDialogTitle>
            <AlertDialogDescription>L'image disparaît de toutes tes lettres. Tu pourras en déposer une autre quand tu veux.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Garder</AlertDialogCancel>
            <AlertDialogAction onClick={() => void run(() => api.deleteSignature(), 'Signature retirée')}>Retirer</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
