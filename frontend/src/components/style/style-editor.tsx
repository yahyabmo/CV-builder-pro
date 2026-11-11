import {
  ChevronDown,
  Columns2,
  Eye,
  EyeOff,
  Frame,
  Heading,
  LayoutTemplate,
  List,
  ListOrdered,
  Palette as PaletteIcon,
  Type,
} from 'lucide-react'
import { useState } from 'react'

import { move, SortableList, SortableRow } from '@/components/editor/sortable'
import type { CvEditor } from '@/hooks/use-cv-editor'
import { useFonts } from '@/hooks/use-fonts'
import { applyPalette, ELEMENTS, elementValue, fromColor, MOODS, PALETTES, samePalette, warnings, type Mood, type Palette } from '@/lib/palettes'
import type { BlockKey, Column, CVContent, CVStyle, PaletteKey, TextStyle } from '@/lib/types'
import { cn } from '@/lib/utils'
import {
  ColorPicker,
  FontPicker,
  Group,
  NumberInput,
  PALETTE,
  resolveColor,
  Row,
  Segmented,
  SliderInput,
  Subhead,
  Toggle,
} from './controls'
import { PhotoPanel } from './photo-panel'
import { ThemesPanel } from './themes-panel'

type UpdateStyle = CvEditor['updateStyle']

interface StyleEditorProps {
  slug: string
  style: CVStyle
  content: CVContent
  editor: CvEditor
}

export function StyleEditor({ slug, style, content, editor }: StyleEditorProps) {
  const set = editor.updateStyle
  return (
    <div className="flex flex-col gap-2.5 pb-24">
      <ThemesPanel style={style} replaceStyle={editor.replaceStyle} baseSlug={editor.detail?.meta.source ?? 'base'} />
      <ColorsGroup style={style} set={set} />
      <TypographyGroup style={style} set={set} />
      <TitlesGroup style={style} set={set} />
      <BulletsGroup style={style} set={set} />
      <FramesGroup style={style} set={set} />
      <PhotoPanel slug={slug} style={style} set={set} editor={editor} />
      <LayoutGroup style={style} set={set} />
      <SectionsGroup content={content} update={editor.update} />
    </div>
  )
}

// ─── Couleurs ────────────────────────────────────────────────────────────────

function ColorsGroup({ style, set }: { style: CVStyle; set: UpdateStyle }) {
  const [mood, setMood] = useState<Mood | null>(null)
  const current = PALETTES.find((p) => samePalette(p.colors, style.palette))
  const alerts = warnings(style.palette)
  const shown = PALETTES.filter((p) => mood === null || p.mood === mood)
  const choose = (colors: Palette) => set((s) => applyPalette(s, colors))
  return (
    <Group title="Couleurs" hint="Ta palette en 8 rôles, une palette prête ou tirée d'une seule couleur." icon={<PaletteIcon className="size-3.5" />} defaultOpen>
      <div className="@container flex flex-col gap-5">
        <section aria-label="Ta palette" className="flex flex-col gap-2">
          <div className="flex items-baseline gap-2">
            <h3 className="text-[12.5px] font-semibold">Ta palette</h3>
            <span className="text-[12px] text-muted-foreground">{current?.name ?? 'Personnalisée'}</span>
          </div>
          <div className="grid grid-cols-2 gap-1.5 @2xl:grid-cols-4">
            {PALETTE.map((role) => (
              <ColorPicker
                key={role.key}
                free
                style={style}
                value={style.palette[role.key]}
                onChange={(v) => v && set((s) => void (s.palette[role.key] = v), `palette.${role.key}`)}
              >
                <button
                  type="button"
                  aria-label={`${role.label} : #${style.palette[role.key]}, changer`}
                  className="flex min-w-0 items-center gap-2 rounded-lg border bg-background p-1.5 text-left transition-colors hover:bg-muted/50"
                >
                  <span className="size-7 shrink-0 rounded-md border border-black/10" style={{ background: `#${style.palette[role.key]}` }} />
                  <span className="flex min-w-0 flex-col">
                    <span className="truncate text-[12px] font-medium">{role.label}</span>
                    <span className="font-mono text-[10.5px] text-muted-foreground">#{style.palette[role.key]}</span>
                  </span>
                </button>
              </ColorPicker>
            ))}
          </div>
          {alerts.map((alert) => (
            <div key={alert.role} role="status" className="flex items-center gap-2.5 rounded-lg bg-status-interview-soft px-3 py-2 text-[12px] text-status-interview">
              <span className="min-w-0 flex-1">{alert.text}</span>
              <button
                type="button"
                onClick={() => set((s) => void (s.palette[alert.role] = alert.fix))}
                className="shrink-0 rounded-md border border-current/30 bg-background px-2 py-1 text-[12px] font-semibold"
              >
                Corriger
              </button>
            </div>
          ))}
        </section>

        <section aria-label="Palettes prêtes" className="flex flex-col gap-2.5">
          <div className="flex items-baseline gap-2">
            <h3 className="text-[12.5px] font-semibold">Palettes prêtes</h3>
            <span className="font-mono text-[11px] text-muted-foreground">{PALETTES.length}</span>
            <span className="text-[11.5px] text-muted-foreground">· les dates, lieux, puces et liens prennent aussi leur couleur</span>
          </div>
          <div role="radiogroup" aria-label="Ambiance" className="flex flex-wrap gap-1.5">
            {[null, ...MOODS].map((m) => (
              <button
                key={m ?? 'toutes'}
                type="button"
                role="radio"
                aria-checked={mood === m}
                onClick={() => setMood(m)}
                className={cn(
                  'h-7 rounded-full border px-2.5 text-[12px] transition-colors',
                  mood === m ? 'border-primary/60 bg-accent font-semibold text-accent-foreground' : 'bg-background hover:bg-muted',
                )}
              >
                {m ?? 'Toutes'}
              </button>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-2 @lg:grid-cols-3">
            {shown.map((p) => (
              <PaletteCard key={p.name} name={p.name} detail={p.mood} colors={p.colors} active={current?.name === p.name} onPick={() => choose(p.colors)} />
            ))}
          </div>
        </section>

        <section aria-label="À partir d'une couleur" className="flex flex-col gap-2">
          <div className="flex flex-col gap-0.5">
            <h3 className="text-[12.5px] font-semibold">À partir d'une couleur</h3>
            <p className="text-[12px] text-muted-foreground">Trois palettes construites autour de ta couleur principale, #{style.palette.primary}.</p>
          </div>
          <div className="grid grid-cols-1 gap-2 @md:grid-cols-3">
            {fromColor(style.palette.primary).map((g) => (
              <button
                key={g.name}
                type="button"
                onClick={() => choose(g.colors)}
                aria-pressed={samePalette(g.colors, style.palette)}
                className={cn(
                  'flex flex-col items-start gap-1.5 rounded-xl border bg-background p-2 text-left transition-colors hover:border-primary/40',
                  samePalette(g.colors, style.palette) && 'border-primary ring-2 ring-primary/15',
                )}
              >
                <Strip colors={g.colors} className="h-6" />
                <span className="text-[12.5px] font-medium">{g.name}</span>
                <span className="text-[11.5px] text-muted-foreground">{g.hint}</span>
              </button>
            ))}
          </div>
        </section>

        <ElementColors style={style} set={set} />
      </div>
    </Group>
  )
}

const ORDERED: PaletteKey[] = ['primary', 'secondary', 'accent', 'text', 'muted', 'band', 'title_band', 'link']

function Strip({ colors, className }: { colors: Palette; className?: string }) {
  return (
    <span aria-hidden className={cn('flex w-full overflow-hidden rounded-[4px]', className)}>
      {ORDERED.map((key) => (
        <span key={key} className="flex-1" style={{ background: `#${colors[key]}` }} />
      ))}
    </span>
  )
}

/** Une palette sur un mini-CV : nom, filet, fond de colonne, titres, texte, accent. */
function PaletteCard({ name, detail, colors, active, onPick }: { name: string; detail: string; colors: Palette; active: boolean; onPick: () => void }) {
  const c = (key: PaletteKey) => `#${colors[key]}`
  return (
    <button
      type="button"
      onClick={onPick}
      aria-pressed={active}
      aria-label={`Palette ${name}`}
      className={cn(
        'flex flex-col items-start gap-1.5 rounded-xl border bg-background p-2 text-left transition-colors hover:border-primary/40',
        active && 'border-primary ring-2 ring-primary/15',
      )}
    >
      <span aria-hidden className="flex h-16 w-full flex-col gap-1 rounded-md border bg-white p-1.5">
        <span className="h-1.5 w-1/2 rounded-[2px]" style={{ background: c('primary') }} />
        <span className="h-px w-full" style={{ background: c('primary') }} />
        <span className="flex flex-1 gap-1.5">
          <span className="flex flex-1 flex-col gap-1 rounded-[2px] p-1" style={{ background: c('band') }}>
            <span className="h-1 w-3/4 rounded-[1px]" style={{ background: c('primary') }} />
            <span className="h-[3px] w-11/12 rounded-[1px] opacity-60" style={{ background: c('muted') }} />
          </span>
          <span className="flex flex-[1.5] flex-col gap-1 pt-0.5">
            <span className="h-1 w-3/4 rounded-[1px]" style={{ background: c('primary') }} />
            <span className="h-[3px] w-full rounded-[1px] opacity-55" style={{ background: c('text') }} />
            <span className="h-[3px] w-2/5 rounded-[1px]" style={{ background: c('accent') }} />
          </span>
        </span>
      </span>
      <span className="flex w-full items-center justify-between gap-1">
        <span className="truncate text-[12px] font-medium">{name}</span>
        <span className="shrink-0 text-[10.5px] text-muted-foreground">{detail}</span>
      </span>
      <Strip colors={colors} className="h-2" />
    </button>
  )
}

/** La couleur de chaque élément du CV : un rôle de la palette, ou une couleur libre. */
function ElementColors({ style, set }: { style: CVStyle; set: UpdateStyle }) {
  const [open, setOpen] = useState(false)
  return (
    <section aria-label="Couleur de chaque élément" className="flex flex-col gap-2">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex items-center gap-1.5 self-start text-[12.5px] font-semibold">
        <ChevronDown className={cn('size-3.5 transition-transform', open && 'rotate-180')} />
        Couleur de chaque élément
      </button>
      {open && (
        <>
          <p className="text-[12px] text-muted-foreground">Chaque élément prend un rôle de ta palette : changer de palette le recolore. Une couleur libre reste possible.</p>
          <div className="grid grid-cols-1 gap-1.5 @lg:grid-cols-2">
            {ELEMENTS.map((element) => {
              const value = elementValue(element, style)
              return (
                <div key={element.id} className="flex items-center gap-2 rounded-lg border bg-background px-2.5 py-1.5">
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="truncate text-[12.5px] font-medium">{element.label}</span>
                    <span className="truncate text-[11px] text-muted-foreground">{element.hint}</span>
                  </span>
                  <ColorPicker
                    style={style}
                    name={element.label}
                    value={value === 'mixed' ? (element.values(style)[0] ?? null) : value}
                    mixed={value === 'mixed'}
                    emptyLabel={element.empty}
                    onChange={(v) => set((s) => element.apply(s, v), `element.${element.id}`)}
                  />
                </div>
              )
            })}
          </div>
        </>
      )}
    </section>
  )
}

// ─── Typographie ─────────────────────────────────────────────────────────────

const BLOCKS: { title: string; items: { key: BlockKey; label: string }[] }[] = [
  {
    title: 'En-tête',
    items: [
      { key: 'name', label: 'Nom' },
      { key: 'headline', label: 'Titre' },
      { key: 'summary', label: 'Accroche' },
      { key: 'contact_label', label: 'Coordonnées : libellés' },
      { key: 'contact_strong', label: 'Coordonnées : en gras' },
      { key: 'contact_value', label: 'Coordonnées : texte' },
    ],
  },
  {
    title: 'Rubriques',
    items: [
      { key: 'section_title', label: 'Titres de rubrique' },
      { key: 'experience_title', label: "Intitulé d'expérience" },
      { key: 'experience_place', label: "Lieu d'expérience" },
      { key: 'experience_tag', label: 'Mention (seul, équipe…)' },
      { key: 'date_in_place', label: 'Dates des expériences' },
      { key: 'entry_title', label: 'Titres (formation, associatif)' },
      { key: 'project_title', label: 'Titres de projet' },
      { key: 'project_tag', label: 'Cadre de projet' },
      { key: 'skill_label', label: 'Groupes de compétences' },
      { key: 'language_name', label: 'Noms de langue' },
      { key: 'date', label: 'Dates' },
    ],
  },
  { title: 'Texte', items: [{ key: 'body', label: 'Texte courant et puces' }] },
]

function TypographyGroup({ style, set }: { style: CVStyle; set: UpdateStyle }) {
  const fonts = useFonts()
  const fontName = (id: string | null) => fonts.find((f) => f.id === (id ?? style.fonts.main))?.name ?? id ?? style.fonts.main
  return (
    <Group title="Polices et texte" hint="Police principale, puis chaque type de texte." icon={<Type className="size-3.5" />}>
      <Row label="Police principale">
        <FontPicker value={style.fonts.main} onChange={(v) => v && set((s) => void (s.fonts.main = v))} />
      </Row>
      <Row label="Taille de base" hint="Taille du texte courant">
        <Segmented
          value={String(style.page.base_size) as '10' | '11' | '12'}
          onChange={(v) => set((s) => void (s.page.base_size = Number(v) as 10 | 11 | 12))}
          options={[{ value: '10', label: '10 pt' }, { value: '11', label: '11 pt' }, { value: '12', label: '12 pt' }]}
        />
      </Row>
      <Row label="Chiffres" hint="Proportionnels : comme le CV d'origine">
        <Segmented
          value={style.fonts.figures}
          onChange={(v) => set((s) => void (s.fonts.figures = v))}
          options={[{ value: 'proportional', label: 'Proportionnels' }, { value: 'tabular', label: 'Alignés' }]}
        />
      </Row>
      <Row label="Ligatures « fi », « fl »" hint="Coupées : un ATS lit mieux le texte">
        <Toggle label="Ligatures" checked={style.fonts.ligatures} onChange={(v) => set((s) => void (s.fonts.ligatures = v))} />
      </Row>
      {BLOCKS.map((group) => (
        <div key={group.title} className="flex flex-col gap-1">
          <Subhead>{group.title}</Subhead>
          {group.items.map((item) => (
            <BlockRow key={item.key} id={item.key} label={item.label} block={style.blocks[item.key]} style={style} fontName={fontName} set={set} />
          ))}
        </div>
      ))}
    </Group>
  )
}

function describe(block: TextStyle, fontName: (id: string | null) => string): string {
  const parts = [fontName(block.font), block.size ? `${String(block.size).replace('.', ',')} pt` : 'taille du texte']
  if (block.bold) parts.push('gras')
  if (block.italic) parts.push('italique')
  if (block.uppercase) parts.push('majuscules')
  return parts.join(' · ')
}

function BlockRow({ id, label, block, style, fontName, set }: { id: BlockKey; label: string; block: TextStyle; style: CVStyle; fontName: (id: string | null) => string; set: UpdateStyle }) {
  const [open, setOpen] = useState(false)
  const edit = (mutate: (b: TextStyle) => void, field: string) => set((s) => mutate(s.blocks[id]), `blocks.${id}.${field}`)
  return (
    <div className={cn('rounded-lg border transition-colors', open ? 'bg-muted/30' : 'border-transparent hover:bg-muted/40')}>
      <button type="button" onClick={() => setOpen(!open)} className="flex w-full items-center gap-2.5 px-2.5 py-1.5 text-left" aria-expanded={open}>
        <span className="size-3 shrink-0 rounded-full border border-black/10" style={{ background: resolveColor(style, block.color) }} />
        <span className="min-w-0 flex-1">
          <span className="block text-[12.5px]">{label}</span>
          <span className="block truncate text-[11px] text-muted-foreground">{describe(block, fontName)}</span>
        </span>
      </button>
      {open && (
        <div className="flex flex-col gap-2 px-2.5 pt-1 pb-2.5">
          <Row label="Police">
            <FontPicker value={block.font} emptyLabel="Police principale" onChange={(v) => edit((b) => void (b.font = v), 'font')} />
          </Row>
          <Row label="Taille">
            <NumberInput value={block.size} emptyLabel="auto" unit="pt" step={0.5} min={6} max={40} onChange={(v) => edit((b) => void (b.size = v), 'size')} />
          </Row>
          <Row label="Interligne">
            <NumberInput value={block.leading} emptyLabel="auto" unit="pt" step={0.5} min={6} max={60} onChange={(v) => edit((b) => void (b.leading = v), 'leading')} />
          </Row>
          <Row label="Style">
            <div className="flex gap-1">
              {(
                [
                  ['bold', 'G', 'Gras', 'font-bold'],
                  ['italic', 'I', 'Italique', 'italic font-serif'],
                  ['uppercase', 'AA', 'Majuscules', 'text-[10px] tracking-wider'],
                ] as const
              ).map(([field, text, title, cls]) => (
                <button
                  key={field}
                  type="button"
                  title={title}
                  aria-pressed={block[field]}
                  onClick={() => edit((b) => void (b[field] = !b[field]), field)}
                  className={cn('flex size-7 items-center justify-center rounded-md border text-[12px] transition-colors', cls, block[field] ? 'border-primary bg-primary text-primary-foreground' : 'bg-background hover:bg-muted')}
                >
                  {text}
                </button>
              ))}
            </div>
          </Row>
          <Row label="Couleur">
            <ColorPicker style={style} value={block.color} emptyLabel="Couleur du texte" onChange={(v) => edit((b) => void (b.color = v), 'color')} />
          </Row>
          <Row label="Espacement des lettres">
            <NumberInput value={block.letter_spacing} unit="%" step={1} min={-5} max={40} onChange={(v) => edit((b) => void (b.letter_spacing = v ?? 0), 'letter_spacing')} />
          </Row>
        </div>
      )}
    </div>
  )
}

// ─── Titres de rubrique ──────────────────────────────────────────────────────

function TitlesGroup({ style, set }: { style: CVStyle; set: UpdateStyle }) {
  const t = style.section_titles
  const sp = style.spacing
  return (
    <Group title="Titres de rubrique" hint="Filet, bandeau ou titre seul." icon={<Heading className="size-3.5" />}>
      <Row label="Présentation">
        <Segmented
          value={t.variant}
          onChange={(v) => set((s) => void (s.section_titles.variant = v))}
          options={[{ value: 'rule', label: 'Filet' }, { value: 'band', label: 'Bandeau' }, { value: 'plain', label: 'Seul' }]}
        />
      </Row>
      {t.variant === 'rule' && (
        <>
          <Row label="Épaisseur du filet">
            <NumberInput value={sp.title_rule_thickness_pt} unit="pt" step={0.1} min={0.1} max={4} onChange={(v) => set((s) => void (s.spacing.title_rule_thickness_pt = v ?? 0.4), 'title_rule_thickness')} />
          </Row>
          <Row label="Couleur du filet">
            <ColorPicker style={style} value={sp.title_rule_color} onChange={(v) => v && set((s) => void (s.spacing.title_rule_color = v))} />
          </Row>
          <Row label="Écart titre – filet">
            <NumberInput value={sp.title_rule_gap_pt} unit="pt" step={0.5} min={0} max={12} onChange={(v) => set((s) => void (s.spacing.title_rule_gap_pt = v ?? 0), 'title_rule_gap')} />
          </Row>
        </>
      )}
      {t.variant === 'band' && (
        <>
          <Row label="Couleur du bandeau">
            <ColorPicker style={style} value={t.band_color} onChange={(v) => v && set((s) => void (s.section_titles.band_color = v))} />
          </Row>
          <Row label="Couleur du texte">
            <ColorPicker style={style} value={t.band_text_color} onChange={(v) => v && set((s) => void (s.section_titles.band_text_color = v))} />
          </Row>
          <Row label="Arrondi">
            <NumberInput value={t.band_radius_pt} unit="pt" step={0.5} min={0} max={20} onChange={(v) => set((s) => void (s.section_titles.band_radius_pt = v ?? 0), 'band_radius')} />
          </Row>
          <Row label="Marge intérieure">
            <NumberInput value={t.band_padding_pt} unit="pt" step={0.5} min={0} max={20} onChange={(v) => set((s) => void (s.section_titles.band_padding_pt = v ?? 0), 'band_padding')} />
          </Row>
        </>
      )}
      <Row label="Espace sous le titre">
        <NumberInput value={sp.after_title_pt} unit="pt" step={0.5} min={0} max={30} onChange={(v) => set((s) => void (s.spacing.after_title_pt = v ?? 0), 'after_title')} />
      </Row>
    </Group>
  )
}

// ─── Puces ───────────────────────────────────────────────────────────────────

function BulletsGroup({ style, set }: { style: CVStyle; set: UpdateStyle }) {
  const l = style.lists
  return (
    <Group title="Puces" hint="Symbole, couleur et retrait des listes." icon={<List className="size-3.5" />}>
      <Row label="Symbole">
        <Segmented
          value={l.bullet}
          onChange={(v) => set((s) => void (s.lists.bullet = v))}
          options={[
            { value: 'bullet', label: '•', title: 'Point' },
            { value: 'dash', label: '–', title: 'Tiret' },
            { value: 'square', label: '▪', title: 'Carré' },
            { value: 'chevron', label: '›', title: 'Chevron' },
          ]}
        />
      </Row>
      <Row label="Couleur">
        <ColorPicker style={style} value={l.bullet_color} emptyLabel="Couleur du texte" onChange={(v) => set((s) => void (s.lists.bullet_color = v))} />
      </Row>
      <Row label="Retrait">
        <NumberInput value={l.leftmargin_pt} unit="pt" step={1} min={0} max={40} onChange={(v) => set((s) => void (s.lists.leftmargin_pt = v ?? 0), 'leftmargin')} />
      </Row>
      <Row label="Écart puce – texte">
        <NumberInput value={l.labelsep_pt} unit="pt" step={0.5} min={0} max={20} onChange={(v) => set((s) => void (s.lists.labelsep_pt = v ?? 0), 'labelsep')} />
      </Row>
      <Row label="Espace entre puces" hint="Colonne de gauche / de droite">
        <NumberInput value={l.left.itemsep_pt} unit="pt" step={0.5} min={0} max={20} width="w-10" onChange={(v) => set((s) => void (s.lists.left.itemsep_pt = v ?? 0), 'itemsep_left')} />
        <NumberInput value={l.right.itemsep_pt} unit="pt" step={0.5} min={0} max={20} width="w-10" onChange={(v) => set((s) => void (s.lists.right.itemsep_pt = v ?? 0), 'itemsep_right')} />
      </Row>
    </Group>
  )
}

// ─── Encadrements ────────────────────────────────────────────────────────────

function FramesGroup({ style, set }: { style: CVStyle; set: UpdateStyle }) {
  const f = style.summary_frame
  const b = style.band
  const h = style.header
  return (
    <Group title="Encadrements et fonds" hint="Cadre de l'accroche, fond de colonne, filet de l'en-tête." icon={<Frame className="size-3.5" />}>
      <Subhead>Accroche</Subhead>
      <Row label="Encadrer l'accroche">
        <Toggle label="Encadrer l'accroche" checked={f.visible} onChange={(v) => set((s) => void (s.summary_frame.visible = v))} />
      </Row>
      {f.visible && (
        <>
          <Row label="Bordure">
            <NumberInput value={f.border_pt} unit="pt" step={0.1} min={0} max={5} onChange={(v) => set((s) => void (s.summary_frame.border_pt = v ?? 0), 'frame_border')} />
            <ColorPicker style={style} value={f.border_color} onChange={(v) => v && set((s) => void (s.summary_frame.border_color = v))} />
          </Row>
          <Row label="Fond">
            <ColorPicker style={style} value={f.background_color} emptyLabel="Sans fond" onChange={(v) => set((s) => void (s.summary_frame.background_color = v))} />
          </Row>
          <Row label="Arrondi">
            <NumberInput value={f.radius_pt} unit="pt" step={0.5} min={0} max={30} onChange={(v) => set((s) => void (s.summary_frame.radius_pt = v ?? 0), 'frame_radius')} />
          </Row>
          <Row label="Marge intérieure">
            <NumberInput value={f.padding_pt} unit="pt" step={0.5} min={0} max={30} onChange={(v) => set((s) => void (s.summary_frame.padding_pt = v ?? 0), 'frame_padding')} />
          </Row>
        </>
      )}
      <Subhead>Fond de colonne</Subhead>
      <Row label="Colonne colorée">
        <Toggle label="Colonne colorée" checked={b.visible} onChange={(v) => set((s) => void (s.band.visible = v))} />
      </Row>
      {b.visible && (
        <>
          <Row label="Colonne">
            <Segmented value={b.column} onChange={(v: Column) => set((s) => void (s.band.column = v))} options={[{ value: 'left', label: 'Gauche' }, { value: 'right', label: 'Droite' }]} />
          </Row>
          <Row label="Couleur">
            <ColorPicker style={style} value={b.color} onChange={(v) => v && set((s) => void (s.band.color = v))} />
          </Row>
        </>
      )}
      <Subhead>En-tête</Subhead>
      <Row label="Filet sous l'en-tête">
        <Toggle label="Filet sous l'en-tête" checked={h.rule_visible} onChange={(v) => set((s) => void (s.header.rule_visible = v))} />
      </Row>
      {h.rule_visible && (
        <Row label="Épaisseur et couleur">
          <NumberInput value={h.rule_thickness_pt} unit="pt" step={0.1} min={0.1} max={4} onChange={(v) => set((s) => void (s.header.rule_thickness_pt = v ?? 0.4), 'header_rule')} />
          <ColorPicker style={style} value={h.rule_color} onChange={(v) => v && set((s) => void (s.header.rule_color = v))} />
        </Row>
      )}
      <Row label="Séparateur des coordonnées">
        <input
          value={h.contact_separator}
          maxLength={3}
          onChange={(e) => set((s) => void (s.header.contact_separator = e.target.value), 'contact_separator')}
          className="h-7 w-12 rounded-md border bg-background text-center text-[13px] shadow-xs outline-none focus:border-ring"
          aria-label="Séparateur"
        />
      </Row>
    </Group>
  )
}

// ─── Mise en page ────────────────────────────────────────────────────────────

const GAP = 0.04 // espace entre les deux colonnes, en part de la largeur

function LayoutGroup({ style, set }: { style: CVStyle; set: UpdateStyle }) {
  const p = style.page
  const c = style.columns
  const sp = style.spacing
  const h = style.header
  return (
    <Group title="Mise en page" hint="Marges, colonnes, interligne et espaces." icon={<LayoutTemplate className="size-3.5" />}>
      <Row label="Marges">
        <NumberInput value={p.margin_cm} unit="cm" step={0.1} min={0.4} max={3} onChange={(v) => set((s) => void (s.page.margin_cm = v ?? 1), 'margin')} />
      </Row>
      <Row label="Interligne">
        <NumberInput value={p.line_spread} step={0.01} min={0.8} max={1.6} onChange={(v) => set((s) => void (s.page.line_spread = v ?? 1), 'line_spread')} />
      </Row>
      <Row label="Espace entre paragraphes">
        <NumberInput value={p.parskip_pt} unit="pt" step={0.5} min={0} max={12} onChange={(v) => set((s) => void (s.page.parskip_pt = v ?? 0), 'parskip')} />
      </Row>
      <Row label="En-tête">
        <Segmented
          value={h.align}
          onChange={(v) => set((s) => void (s.header.align = v))}
          options={[
            { value: 'left', label: 'À gauche' },
            { value: 'center', label: 'Centré' },
          ]}
        />
      </Row>
      <Subhead>Colonnes</Subhead>
      <Row label="Mise en page" hint={c.layout === 'one' ? "Les rubriques l'une sous l'autre, dans l'ordre du contenu" : undefined}>
        <Segmented
          value={c.layout}
          onChange={(v) => set((s) => void (s.columns.layout = v))}
          options={[
            { value: 'two', label: 'Deux colonnes' },
            { value: 'one', label: 'Une colonne' },
          ]}
        />
      </Row>
      {c.layout === 'two' && (
        <>
          <Row label="Largeur de la colonne de gauche">
            <SliderInput
              value={c.left_width}
              min={0.25}
              max={0.6}
              step={0.01}
              format={(v) => `${Math.round(v * 100)} %`}
              onChange={(v) =>
                set((s) => {
                  s.columns.left_width = Math.round(v * 100) / 100
                  s.columns.right_width = Math.round((1 - GAP - v) * 100) / 100
                }, 'columns')
              }
            />
          </Row>
          <Row label="Remplir toute la page" hint="L'espace libre se répartit entre les rubriques">
            <Toggle label="Remplir la page" checked={c.fill_page} onChange={(v) => set((s) => void (s.columns.fill_page = v))} />
          </Row>
        </>
      )}
      <Subhead>Espaces</Subhead>
      <Row label="Avant chaque rubrique" hint="Minimum, avant répartition">
        <NumberInput value={sp.section_gap_pt} unit="pt" step={1} min={0} max={40} onChange={(v) => set((s) => void (s.spacing.section_gap_pt = v ?? 0), 'section_gap')} />
      </Row>
      <Row label="Entre deux entrées">
        <NumberInput value={sp.entry_gap_pt} unit="pt" step={0.5} min={0} max={30} onChange={(v) => set((s) => void (s.spacing.entry_gap_pt = v ?? 0), 'entry_gap')} />
      </Row>
      <Row label="Entre deux groupes de compétences">
        <NumberInput value={sp.skill_gap_pt} unit="pt" step={0.5} min={0} max={30} onChange={(v) => set((s) => void (s.spacing.skill_gap_pt = v ?? 0), 'skill_gap')} />
      </Row>
      <Row label="Sous le nom">
        <NumberInput value={h.name_gap_pt} unit="pt" step={0.5} min={0} max={30} onChange={(v) => set((s) => void (s.header.name_gap_pt = v ?? 0), 'name_gap')} />
      </Row>
      <Row label="Sous le titre">
        <NumberInput value={h.headline_gap_pt} unit="pt" step={0.5} min={0} max={30} onChange={(v) => set((s) => void (s.header.headline_gap_pt = v ?? 0), 'headline_gap')} />
      </Row>
      <Row label="Sous les coordonnées">
        <NumberInput value={h.after_contact_pt} unit="pt" step={0.5} min={0} max={40} onChange={(v) => set((s) => void (s.header.after_contact_pt = v ?? 0), 'after_contact')} />
      </Row>
      <Subhead>Liens</Subhead>
      <Row label="Cadres autour des liens" hint="Visibles à l'écran seulement, jamais à l'impression">
        <Toggle label="Cadres des liens" checked={!style.links.hide_boxes} onChange={(v) => set((s) => void (s.links.hide_boxes = !v))} />
      </Row>
    </Group>
  )
}

// ─── Ordre des sections ──────────────────────────────────────────────────────

function SectionsGroup({ content, update }: { content: CVContent; update: CvEditor['update'] }) {
  return (
    <Group title="Ordre des sections" hint="Glisser pour réordonner, l'œil pour masquer." icon={<ListOrdered className="size-3.5" />}>
      <div className="grid grid-cols-2 gap-3">
        {(['left', 'right'] as const).map((column) => {
          const sections = content.sections.filter((s) => s.column === column)
          const ids = sections.map((s) => s.id)
          return (
            <div key={column} className="flex flex-col gap-1">
              <Subhead>
                <Columns2 className="mr-1 inline size-3" />
                {column === 'left' ? 'Gauche' : 'Droite'}
              </Subhead>
              <SortableList
                ids={ids}
                onMove={(from, to) =>
                  update((d) => {
                    const order = d.sections.filter((s) => s.column === column)
                    move(order, from, to)
                    const others = d.sections.filter((s) => s.column !== column)
                    d.sections = column === 'left' ? [...order, ...others] : [...others, ...order]
                  })
                }
              >
                {sections.map((section) => (
                  <SortableRow key={section.id} id={section.id}>
                    {(handle) => (
                      <div className={cn('flex items-center gap-1 rounded-md border bg-background py-0.5 pr-1 text-[12px]', !section.visible && 'opacity-50')}>
                        {handle}
                        <span className="min-w-0 flex-1 truncate">{section.title}</span>
                        <button
                          type="button"
                          aria-label={section.visible ? 'Masquer' : 'Afficher'}
                          onClick={() => update((d) => {
                            const target = d.sections.find((s) => s.id === section.id)
                            if (target) target.visible = !target.visible
                          })}
                          className="flex size-6 items-center justify-center rounded text-muted-foreground hover:bg-muted"
                        >
                          {section.visible ? <Eye className="size-3.5" /> : <EyeOff className="size-3.5" />}
                        </button>
                      </div>
                    )}
                  </SortableRow>
                ))}
              </SortableList>
            </div>
          )
        })}
      </div>
    </Group>
  )
}

