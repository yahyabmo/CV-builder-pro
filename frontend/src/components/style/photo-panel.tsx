import { Image as ImageIcon, Loader2, Upload } from 'lucide-react'
import { useRef, useState } from 'react'
import Cropper, { type Area } from 'react-easy-crop'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Slider } from '@/components/ui/slider'
import type { CvEditor } from '@/hooks/use-cv-editor'
import { api } from '@/lib/api'
import type { CVStyle } from '@/lib/types'
import { cn } from '@/lib/utils'
import { ColorPicker, Group, NumberInput, Row, Segmented, Toggle } from './controls'

interface PhotoPanelProps {
  slug: string
  style: CVStyle
  set: CvEditor['updateStyle']
  editor: CvEditor
}

export function PhotoPanel({ slug, style, set, editor }: PhotoPanelProps) {
  const p = style.photo
  const input = useRef<HTMLInputElement>(null)
  const [source, setSource] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)

  const onFile = (file: File | undefined) => {
    if (!file) return
    if (!file.type.startsWith('image/')) {
      toast.error("Ce fichier n'est pas une image")
      return
    }
    setSource(URL.createObjectURL(file))
  }

  const onCropped = async (blob: Blob) => {
    if (source) URL.revokeObjectURL(source)
    setSource(null)
    setUploading(true)
    try {
      await editor.uploadPhoto(blob)
      toast.success('Photo remplacée')
    } catch (error) {
      toast.error("La photo n'a pas pu être importée", { description: error instanceof Error ? error.message : String(error) })
    } finally {
      setUploading(false)
    }
  }

  const radius = p.shape === 'circle' ? '9999px' : p.shape === 'rounded' ? `${Math.min(p.corner_radius_pt, 30) * 1.4}px` : '2px'

  return (
    <Group title="Photo" hint="Importer, recadrer, forme, bordure, taille, position." icon={<ImageIcon className="size-3.5" />}>
      <div className="flex items-center gap-4">
        <div className="relative size-20 shrink-0 overflow-hidden bg-muted" style={{ borderRadius: radius, outline: p.border_pt ? `${Math.max(1, p.border_pt)}px solid #${style.palette.primary}` : undefined }}>
          <img src={api.photoUrl(slug, editor.photoVersion || undefined)} alt="Photo du CV" className={cn('size-full object-cover', !p.visible && 'opacity-30')} />
          {uploading && (
            <div className="absolute inset-0 flex items-center justify-center bg-background/60">
              <Loader2 className="size-5 animate-spin" />
            </div>
          )}
        </div>
        <div className="flex flex-col gap-2">
          <Button variant="outline" size="sm" className="h-8 gap-1.5 text-[12px]" disabled={uploading} onClick={() => input.current?.click()}>
            <Upload className="size-3.5" /> Changer la photo
          </Button>
          <input ref={input} type="file" accept="image/*" className="hidden" onChange={(e) => { onFile(e.target.files?.[0]); e.target.value = '' }} />
          <span className="text-[11px] text-muted-foreground">JPEG, PNG ou WebP. Tu la recadres ensuite.</span>
        </div>
      </div>
      <Row label="Afficher la photo">
        <Toggle label="Afficher la photo" checked={p.visible} onChange={(v) => set((s) => void (s.photo.visible = v))} />
      </Row>
      <Row label="Forme">
        <Segmented value={p.shape} onChange={(v) => set((s) => void (s.photo.shape = v))} options={[{ value: 'square', label: 'Carrée' }, { value: 'rounded', label: 'Arrondie' }, { value: 'circle', label: 'Ronde' }]} />
      </Row>
      {p.shape === 'rounded' && (
        <Row label="Arrondi des coins">
          <NumberInput value={p.corner_radius_pt} unit="pt" step={1} min={1} max={50} onChange={(v) => set((s) => void (s.photo.corner_radius_pt = v ?? 6), 'photo_radius')} />
        </Row>
      )}
      <Row label="Bordure">
        <NumberInput value={p.border_pt} unit="pt" step={0.2} min={0} max={10} onChange={(v) => set((s) => void (s.photo.border_pt = v ?? 0), 'photo_border')} />
        <ColorPicker style={style} value={p.border_color} onChange={(v) => v && set((s) => void (s.photo.border_color = v))} />
      </Row>
      <Row label="Taille" hint={p.size_mode === 'match_text' ? 'Côté = hauteur du texte à côté' : undefined}>
        <Segmented value={p.size_mode} onChange={(v) => set((s) => void (s.photo.size_mode = v))} options={[{ value: 'match_text', label: 'Auto' }, { value: 'fixed', label: 'Fixe' }]} />
        {p.size_mode === 'fixed' && (
          <NumberInput value={p.size_cm} unit="cm" step={0.1} min={1} max={8} onChange={(v) => set((s) => void (s.photo.size_cm = v ?? 3), 'photo_size')} />
        )}
      </Row>
      <Row label="Position">
        <Segmented value={p.position} onChange={(v) => set((s) => void (s.photo.position = v))} options={[{ value: 'left', label: 'À gauche' }, { value: 'right', label: 'À droite' }]} />
      </Row>
      <Row label="Décalage" hint="Horizontal, vertical (vers le bas)">
        <NumberInput value={p.offset_x_pt} unit="pt" step={1} min={-40} max={40} width="w-10" onChange={(v) => set((s) => void (s.photo.offset_x_pt = v ?? 0), 'photo_x')} />
        <NumberInput value={p.offset_y_pt} unit="pt" step={1} min={-40} max={40} width="w-10" onChange={(v) => set((s) => void (s.photo.offset_y_pt = v ?? 0), 'photo_y')} />
      </Row>
      <CropDialog source={source} round={p.shape === 'circle'} onCancel={() => { if (source) URL.revokeObjectURL(source); setSource(null) }} onDone={onCropped} />
    </Group>
  )
}

// ─── Recadrage ───────────────────────────────────────────────────────────────

const OUTPUT_SIDE = 900

async function cropToBlob(source: string, area: Area): Promise<Blob> {
  const image = new Image()
  image.src = source
  await image.decode()
  const side = Math.min(OUTPUT_SIDE, Math.round(area.width))
  const canvas = document.createElement('canvas')
  canvas.width = side
  canvas.height = side
  const context = canvas.getContext('2d')
  if (!context) throw new Error('Canevas indisponible')
  context.imageSmoothingQuality = 'high'
  context.drawImage(image, area.x, area.y, area.width, area.height, 0, 0, side, side)
  return new Promise((resolve, reject) =>
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('Image non générée'))), 'image/jpeg', 0.92),
  )
}

function CropDialog({ source, round, onCancel, onDone }: { source: string | null; round: boolean; onCancel: () => void; onDone: (blob: Blob) => void }) {
  const [crop, setCrop] = useState({ x: 0, y: 0 })
  const [zoom, setZoom] = useState(1)
  const [area, setArea] = useState<Area | null>(null)
  const [busy, setBusy] = useState(false)
  const confirm = async () => {
    if (!source || !area) return
    setBusy(true)
    try {
      onDone(await cropToBlob(source, area))
    } finally {
      setBusy(false)
      setZoom(1)
      setCrop({ x: 0, y: 0 })
    }
  }
  return (
    <Dialog open={source !== null} onOpenChange={(open) => !open && onCancel()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Recadrer la photo</DialogTitle>
          <DialogDescription>Glisse l'image et règle le zoom. Le carré devient la photo du CV.</DialogDescription>
        </DialogHeader>
        <div className="relative h-72 overflow-hidden rounded-lg bg-muted">
          {source && (
            <Cropper
              image={source}
              crop={crop}
              zoom={zoom}
              aspect={1}
              cropShape={round ? 'round' : 'rect'}
              showGrid={!round}
              onCropChange={setCrop}
              onZoomChange={setZoom}
              onCropComplete={(_, pixels) => setArea(pixels)}
            />
          )}
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[12px] text-muted-foreground">Zoom</span>
          <Slider value={[zoom]} min={1} max={4} step={0.01} onValueChange={([v]) => setZoom(v)} />
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onCancel}>Annuler</Button>
          <Button onClick={() => void confirm()} disabled={busy || !area}>
            {busy && <Loader2 className="size-4 animate-spin" />} Utiliser cette photo
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
