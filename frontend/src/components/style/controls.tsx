import { Check, ChevronDown, Minus, Pipette, Plus } from 'lucide-react'
import { useEffect, useId, useState, type ReactNode } from 'react'

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Slider } from '@/components/ui/slider'
import { Switch } from '@/components/ui/switch'
import { useFonts } from '@/hooks/use-fonts'
import { fromHsl, toHsl } from '@/lib/colors'
import { ROLES } from '@/lib/palettes'
import type { CVStyle, PaletteKey } from '@/lib/types'
import { cn } from '@/lib/utils'

// ─── Mise en page des réglages ───────────────────────────────────────────────

/** Un groupe de réglages repliable. */
export function Group({ title, hint, icon, defaultOpen = false, children }: { title: string; hint?: string; icon: ReactNode; defaultOpen?: boolean; children: ReactNode }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <Collapsible open={open} onOpenChange={setOpen} className="rounded-xl border bg-card surface">
      <CollapsibleTrigger className="flex w-full items-center gap-2.5 rounded-xl px-3.5 py-3 text-left transition-colors hover:bg-muted/40">
        <span className="flex size-7 items-center justify-center rounded-lg bg-muted text-muted-foreground">{icon}</span>
        <span className="flex-1">
          <span className="block text-[13px] font-semibold tracking-tight">{title}</span>
          {hint && <span className="block text-[11px] text-muted-foreground">{hint}</span>}
        </span>
        <ChevronDown className={cn('size-4 text-muted-foreground transition-transform duration-200', open && 'rotate-180')} />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="flex flex-col gap-3 border-t px-3.5 pt-3 pb-4">{children}</div>
      </CollapsibleContent>
    </Collapsible>
  )
}

/** Un sous-titre à l'intérieur d'un groupe. */
export function Subhead({ children }: { children: ReactNode }) {
  return <p className="pt-1 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">{children}</p>
}

/** Une ligne : libellé à gauche, contrôle à droite. */
export function Row({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="flex min-h-8 items-center justify-between gap-3">
      <span className="min-w-0 text-[12.5px]">
        {label}
        {hint && <span className="block text-[11px] text-muted-foreground">{hint}</span>}
      </span>
      <div className="flex shrink-0 items-center gap-2">{children}</div>
    </div>
  )
}

// ─── Contrôles ───────────────────────────────────────────────────────────────

interface NumberProps {
  value: number | null
  onChange: (value: number | null) => void
  min?: number
  max?: number
  step?: number
  unit?: string
  /** Valeur vide permise : affichée comme ce texte (ex. « auto »). */
  emptyLabel?: string
  width?: string
}

/** Un nombre avec unité, boutons − et +, et saisie directe. */
export function NumberInput({ value, onChange, min = -Infinity, max = Infinity, step = 1, unit, emptyLabel, width = 'w-14' }: NumberProps) {
  const [text, setText] = useState(value === null ? '' : String(value))
  useEffect(() => setText(value === null ? '' : String(value)), [value])
  const clamp = (n: number) => Math.round(Math.min(max, Math.max(min, n)) * 1000) / 1000
  const commit = (raw: string) => {
    const cleaned = raw.trim().replace(',', '.')
    if (cleaned === '' && emptyLabel) return onChange(null)
    const n = Number(cleaned)
    if (Number.isFinite(n)) onChange(clamp(n))
    else setText(value === null ? '' : String(value))
  }
  const nudge = (direction: 1 | -1) => onChange(clamp((value ?? (min > -Infinity ? min : 0)) + direction * step))
  return (
    <div className="flex h-7 items-center rounded-md border bg-background shadow-xs focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/40">
      <button type="button" aria-label="Diminuer" onClick={() => nudge(-1)} className="flex h-full w-6 items-center justify-center text-muted-foreground hover:text-foreground">
        <Minus className="size-3" />
      </button>
      <input
        inputMode="decimal"
        value={text}
        placeholder={emptyLabel}
        onChange={(e) => setText(e.target.value)}
        onBlur={(e) => commit(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') commit((e.target as HTMLInputElement).value)
          if (e.key === 'ArrowUp') { e.preventDefault(); nudge(1) }
          if (e.key === 'ArrowDown') { e.preventDefault(); nudge(-1) }
        }}
        className={cn('h-full bg-transparent text-center text-[12px] tabular-nums outline-none placeholder:text-muted-foreground', width)}
      />
      {unit && <span className="pr-1 text-[11px] text-muted-foreground">{unit}</span>}
      <button type="button" aria-label="Augmenter" onClick={() => nudge(1)} className="flex h-full w-6 items-center justify-center text-muted-foreground hover:text-foreground">
        <Plus className="size-3" />
      </button>
    </div>
  )
}

/** Un curseur avec sa valeur. */
export function SliderInput({ value, onChange, min, max, step, format }: { value: number; onChange: (v: number) => void; min: number; max: number; step: number; format: (v: number) => string }) {
  return (
    <div className="flex w-48 items-center gap-3">
      <Slider value={[value]} min={min} max={max} step={step} onValueChange={([v]) => onChange(v)} />
      <span className="w-12 text-right text-[12px] tabular-nums text-muted-foreground">{format(value)}</span>
    </div>
  )
}

/** Un choix parmi quelques options, en boutons accolés. */
export function Segmented<T extends string>({ value, onChange, options }: { value: T; onChange: (v: T) => void; options: { value: T; label: ReactNode; title?: string }[] }) {
  return (
    <div role="radiogroup" className="flex rounded-lg bg-muted p-0.5">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          title={option.title}
          aria-checked={value === option.value}
          onClick={() => onChange(option.value)}
          className={cn(
            'flex h-6 items-center gap-1 rounded-md px-2.5 text-[12px] transition-colors',
            value === option.value ? 'bg-background text-foreground shadow-xs' : 'text-muted-foreground hover:text-foreground',
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return <Switch checked={checked} onCheckedChange={onChange} aria-label={label} />
}

// ─── Couleurs ────────────────────────────────────────────────────────────────

export const PALETTE = ROLES

/** La couleur réelle (#RRGGBB) d'une valeur de style : nom de palette ou hexadécimal. */
export function resolveColor(style: CVStyle, value: string | null): string {
  if (value === null) return `#${style.palette.text}`
  if (value in style.palette) return `#${style.palette[value as PaletteKey]}`
  return `#${value}`
}

const HEX = /^#?([0-9a-fA-F]{6})$/

// Le nuancier : 12 familles en 8 nuances (du plus clair au plus foncé), puis les gris.
const FAMILIES: [number, string][] = [
  [0, 'rouge'],
  [18, 'corail'],
  [32, 'orange'],
  [45, 'ocre'],
  [95, 'olive'],
  [145, 'vert'],
  [170, 'émeraude'],
  [190, 'turquoise'],
  [212, 'bleu'],
  [232, 'indigo'],
  [268, 'violet'],
  [320, 'framboise'],
]
const SWATCHES = [94, 86, 76, 64, 52, 42, 32, 22].flatMap((light) =>
  FAMILIES.map(([hue, name]) => ({ hex: fromHsl(hue, light > 80 ? 70 : 62, light), name })),
)
const GRAYS = [97, 90, 80, 68, 55, 42, 30, 20, 14, 10, 7, 4].map((light) => ({ hex: fromHsl(225, 10, light), name: 'gris' }))

const RECENT = 'cv-builder.recent-colors'

function readRecent(): string[] {
  try {
    const found: unknown = JSON.parse(localStorage.getItem(RECENT) ?? '[]')
    return Array.isArray(found) ? found.filter((v): v is string => typeof v === 'string' && HEX.test(v)).slice(0, 8) : []
  } catch {
    return []
  }
}

function remember(hex: string) {
  try {
    localStorage.setItem(RECENT, JSON.stringify([hex, ...readRecent().filter((h) => h !== hex)].slice(0, 8)))
  } catch {
    /* le nuancier marche sans */
  }
}

type EyeDropperCtor = new () => { open: () => Promise<{ sRGBHex: string }> }

interface ColorPickerProps {
  style: CVStyle
  value: string | null
  onChange: (value: string | null) => void
  /** Libellé du choix « vide », si la couleur peut être vide (ex. « Couleur du texte »). */
  emptyLabel?: string
  /** Sans les rôles de la palette : pour choisir la couleur d'un rôle lui-même. */
  free?: boolean
  /** Les réglages concernés n'ont pas tous la même couleur. */
  mixed?: boolean
  /** Le nom du réglage, lu par les lecteurs d'écran. */
  name?: string
  /** Un autre bouton pour ouvrir le nuancier. */
  children?: ReactNode
}

/** Une pastille qui ouvre le nuancier : rôles de la palette, familles de couleurs, nuances, code. */
export function ColorPicker({ style, value, onChange, emptyLabel, free, mixed, name, children }: ColorPickerProps) {
  const current = resolveColor(style, value).slice(1).toUpperCase()
  const [hex, setHex] = useState(current)
  const [recent, setRecent] = useState<string[]>([])
  useEffect(() => setHex(current), [current])
  const id = useId()
  const role = PALETTE.find((p) => p.key === value)
  const label = mixed ? 'Mixte' : value === null ? emptyLabel : (role?.label ?? `#${value}`)
  const dropper = (window as unknown as { EyeDropper?: EyeDropperCtor }).EyeDropper

  const choose = (next: string) => {
    onChange(next)
    remember(next)
    setRecent(readRecent())
  }
  const [hue, sat] = toHsl(current)
  const shades = [94, 86, 76, 64, 52, 42, 32, 22, 14].map((light) => fromHsl(hue, Math.max(sat, 8), light))
  const chosen = (candidate: string) => !role && value !== null && candidate === value.toUpperCase()

  return (
    <Popover onOpenChange={(open) => open && setRecent(readRecent())}>
      <PopoverTrigger asChild>
        {children ?? (
          <button
            type="button"
            aria-label={name ? `${name} : ${label}` : undefined}
            className="flex h-7 items-center gap-2 rounded-md border bg-background px-2 text-[12px] shadow-xs hover:bg-muted/50"
          >
            <span className="size-4 rounded-sm border border-black/10" style={{ background: `#${current}` }} />
            <span className="max-w-28 truncate">{label}</span>
          </button>
        )}
      </PopoverTrigger>
      <PopoverContent align="end" className="flex w-[21rem] flex-col gap-3 p-3">
        {!free && (
          <div className="flex flex-col gap-1.5">
            <p className="text-[11px] font-medium text-muted-foreground">Ta palette</p>
            <div className="grid grid-cols-8 gap-1">
              {PALETTE.map((p) => (
                <button
                  key={p.key}
                  type="button"
                  title={`${p.label} · #${style.palette[p.key]}`}
                  aria-label={p.label}
                  aria-pressed={value === p.key}
                  onClick={() => onChange(p.key)}
                  className={cn('relative aspect-square rounded-md border border-black/10 ring-offset-2 ring-offset-popover', value === p.key && 'ring-2 ring-foreground')}
                  style={{ background: `#${style.palette[p.key]}` }}
                >
                  {value === p.key && <Check className="absolute inset-0 m-auto size-3.5 text-white mix-blend-difference" />}
                </button>
              ))}
            </div>
          </div>
        )}
        <div className="flex flex-col gap-1.5">
          <p className="text-[11px] font-medium text-muted-foreground">Nuancier</p>
          <div className="grid grid-cols-12 gap-1">
            {[...SWATCHES, ...GRAYS].map((swatch) => (
              <button
                key={`${swatch.name}-${swatch.hex}`}
                type="button"
                title={`${swatch.name} · #${swatch.hex}`}
                aria-label={`${swatch.name} #${swatch.hex}`}
                onClick={() => choose(swatch.hex)}
                className={cn('aspect-square rounded-[5px] border border-black/10 ring-offset-1 ring-offset-popover transition-transform hover:scale-110', chosen(swatch.hex) && 'ring-2 ring-foreground')}
                style={{ background: `#${swatch.hex}` }}
              />
            ))}
          </div>
        </div>
        <div className="flex flex-col gap-1.5">
          <p className="text-[11px] font-medium text-muted-foreground">Nuances de la couleur choisie</p>
          <div className="flex gap-1">
            {shades.map((shade) => (
              <button
                key={shade}
                type="button"
                title={`#${shade}`}
                aria-label={`nuance #${shade}`}
                onClick={() => choose(shade)}
                className="h-6 flex-1 rounded-[5px] border border-black/10 transition-transform hover:scale-110"
                style={{ background: `#${shade}` }}
              />
            ))}
          </div>
        </div>
        <div className="flex items-center gap-2 border-t pt-2.5">
          {recent.length > 0 && (
            <div className="flex items-center gap-1" aria-label="Couleurs récentes">
              {recent.slice(0, 5).map((r) => (
                <button key={r} type="button" title={`#${r}`} aria-label={`récente #${r}`} onClick={() => choose(r)} className="size-5 rounded-[5px] border border-black/10" style={{ background: `#${r}` }} />
              ))}
            </div>
          )}
          <div className="ml-auto flex h-7 w-[6.5rem] items-center rounded-md border px-2 font-mono text-[12px]">
            <span className="text-muted-foreground">#</span>
            <input
              id={id}
              value={hex}
              maxLength={7}
              aria-label="Code de la couleur"
              onChange={(e) => {
                setHex(e.target.value.toUpperCase())
                const match = HEX.exec(e.target.value)
                if (match) choose(match[1].toUpperCase())
              }}
              className="w-full bg-transparent outline-none"
            />
          </div>
          {dropper && (
            <button
              type="button"
              title="Prendre une couleur à l'écran"
              aria-label="Pipette"
              onClick={() =>
                new dropper().open().then(
                  (found) => choose(found.sRGBHex.replace('#', '').toUpperCase()),
                  () => undefined,
                )
              }
              className="flex size-7 items-center justify-center rounded-md border text-muted-foreground hover:text-foreground"
            >
              <Pipette className="size-3.5" />
            </button>
          )}
        </div>
        {emptyLabel && !free && (
          <button type="button" onClick={() => onChange(null)} className={cn('rounded-md border px-2 py-1.5 text-left text-[12px] hover:bg-muted', value === null && !mixed && 'border-ring')}>
            {emptyLabel}
          </button>
        )}
      </PopoverContent>
    </Popover>
  )
}

// ─── Polices ─────────────────────────────────────────────────────────────────

/** Le choix d'une police ; chaque nom s'affiche dans sa propre police. */
export function FontPicker({ value, onChange, emptyLabel }: { value: string | null; onChange: (v: string | null) => void; emptyLabel?: string }) {
  const fonts = useFonts()
  const EMPTY = '__main__'
  return (
    <Select value={value ?? EMPTY} onValueChange={(v) => onChange(v === EMPTY ? null : v)}>
      <SelectTrigger size="sm" className="h-7 w-44 text-[12px]">
        <SelectValue />
      </SelectTrigger>
      <SelectContent className="max-h-80">
        {emptyLabel && <SelectItem value={EMPTY} className="text-[12px]">{emptyLabel}</SelectItem>}
        {(['sans', 'serif'] as const).map((category) => (
          <SelectGroup key={category}>
            <SelectLabel className="text-[11px]">{category === 'sans' ? 'Sans empattement' : 'Avec empattement'}</SelectLabel>
            {fonts
              .filter((f) => f.category === category)
              .map((f) => (
                <SelectItem key={f.id} value={f.id} className="text-[13px]">
                  <span style={{ fontFamily: `"CVB ${f.id}", sans-serif` }}>{f.name}</span>
                </SelectItem>
              ))}
          </SelectGroup>
        ))}
      </SelectContent>
    </Select>
  )
}
