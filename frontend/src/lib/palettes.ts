import { contrast, fromHsl, ratioLabel, readableOn, toHsl } from './colors'
import type { CVStyle, PaletteKey, TextStyle } from './types'

export type Palette = Record<PaletteKey, string>

/** Les rôles de la palette, dans l'ordre de l'interface. */
export const ROLES: { key: PaletteKey; label: string }[] = [
  { key: 'primary', label: 'Principale' },
  { key: 'secondary', label: 'Secondaire' },
  { key: 'accent', label: 'Accent' },
  { key: 'text', label: 'Texte' },
  { key: 'muted', label: 'Texte discret' },
  { key: 'band', label: 'Fond de colonne' },
  { key: 'title_band', label: 'Fond des titres' },
  { key: 'link', label: 'Liens' },
]

const ORDER: PaletteKey[] = ['primary', 'secondary', 'accent', 'text', 'muted', 'band', 'title_band', 'link']

export const MOODS = ['Sobres', 'Chaleureuses', 'Vives', 'Pastel', 'Monochromes'] as const
export type Mood = (typeof MOODS)[number]

export interface NamedPalette {
  name: string
  mood: Mood
  colors: Palette
}

// Nom, ambiance, puis les 8 couleurs dans l'ordre de ORDER. Chaque texte passe
// 4,5:1 sur le blanc et sur son fond de colonne, la principale aussi sur le fond des titres.
const RAW: [string, Mood, string][] = [
  ['Marine', 'Sobres', '001F82 4F6B8A 2E7D32 1A1A1A 5B6472 ECF3FB E3EAF6 1F4FA3'],
  ['Ardoise', 'Sobres', '2F3E4E 5F7182 3C7A89 1C232B 5F6874 EEF1F4 E3E8ED 2F5D7C'],
  ['Encre', 'Sobres', '1B2A41 4A5A73 9C7A43 161A20 5A616E F2F3F6 E6E8EE 2E4D7A'],
  ['Graphite', 'Sobres', '2B2B2B 6A6A6A 0F766E 141414 646464 F2F2F2 E6E6E6 0F5E8C'],
  ['Bleu acier', 'Sobres', '1F4E79 5B7FA6 B9741F 1A1F26 5A6370 EDF2F7 DFE8F1 1F5FA8'],
  ['Forêt', 'Sobres', '1E4D3A 5E7F6E 94702A 18201C 5A665F EEF3EF E1EAE3 22684F'],
  ['Terre cuite', 'Chaleureuses', '9C3D24 B07A5A 2F6B6B 2A1D18 6A5D55 F8EFEA F1E2D8 9C4A2E'],
  ['Bordeaux', 'Chaleureuses', '6D1B2E 9A5A66 A47A2F 241418 655559 F7EEF0 EFDDE2 7D2A3F'],
  ['Ocre', 'Chaleureuses', '8A5A12 B08A4A 3F6E5A 241C12 675E4F FAF4E8 F2E6CC 8A5A12'],
  ['Cuivre', 'Chaleureuses', '8C4A2F A9785E 2E5E7A 231A16 675D57 F7F0EB EEDFD5 7A4B33'],
  ['Brique', 'Chaleureuses', '7A2E1F A0624F 3D6A73 22191A 665A57 F6EEEA EEDCD4 7A2E1F'],
  ['Prune', 'Chaleureuses', '5B2A5E 8C6A8E A8782F 1F1720 605561 F5F0F6 EADFEB 6B3A70'],
  ['Indigo', 'Vives', '2E43A3 5C6FC7 C9661F 1B1E2B 5A6173 EEF1FB E1E6F8 2E43A3'],
  ['Émeraude', 'Vives', '0B7552 3FA37F B8861C 13201B 56665F ECF7F2 DBF0E6 0B7552'],
  ['Corail', 'Vives', 'B63730 E0857F 1E6F8C 2A1B1A 685958 FDF0EF FADCDA B5352E'],
  ['Turquoise', 'Vives', '0E747C 4FAAB2 C95F2B 152224 556567 EAF6F7 D5EEF0 0E6C75'],
  ['Violet', 'Vives', '5B3CC4 8A72DB B98200 1D1A2B 5D596D F2EFFC E4DEF8 5B3CC4'],
  ['Orange', 'Vives', 'A64A0A E08A45 1F5E8C 26190F 685D52 FDF2E9 FBE2CC A2480A'],
  ['Lavande', 'Pastel', '6F5BA8 A496CF 4F8C7A 2A2633 656072 F5F3FB EAE6F6 5E4C99'],
  ['Menthe', 'Pastel', '307363 8CC7B5 B08240 1F2A27 5A6963 F1F8F5 E0F0EA 2F7A66'],
  ['Pêche', 'Pastel', '9D5439 E3A68F 4E7F96 2B211E 685C58 FDF4F0 F9E4DB A85A40'],
  ['Ciel', 'Pastel', '356CA4 93BDE3 B97A2C 1C2733 586573 F1F7FD DFEDF9 2F6CA6'],
  ['Rose poudré', 'Pastel', '9F4968 D59AAE 4F7D6D 2B1E23 685A60 FBF2F5 F4E0E7 944060'],
  ['Sable', 'Pastel', '7D6649 BFA98A 4F7A86 2A251F 676057 FAF7F2 F1EBE0 6F5C44'],
  ['Noir et blanc', 'Monochromes', '111111 555555 111111 111111 5E5E5E F4F4F4 EAEAEA 111111'],
  ['Bleu nuit', 'Monochromes', '13294B 3E5C86 13294B 13294B 55657C EEF2F8 DDE5F1 13294B'],
  ['Vert sapin', 'Monochromes', '1F5135 4F7F63 1F5135 1A2A21 57655D EFF5F1 DDEAE2 1F5135'],
  ['Gris chaud', 'Monochromes', '3D3A36 75706A 3D3A36 252320 66625C F4F2EF E8E5E0 3D3A36'],
  ['Grenat', 'Monochromes', '5C1A28 8B4A57 5C1A28 2A1519 675459 F7EFF1 ECDCE0 5C1A28'],
  ['Pétrole', 'Monochromes', '0E4F5C 3F7B86 0E4F5C 142629 546467 EEF5F6 DBEAEC 0E4F5C'],
]

function palette(hexes: string[]): Palette {
  return Object.fromEntries(ORDER.map((key, i) => [key, hexes[i]])) as Palette
}

export const PALETTES: NamedPalette[] = RAW.map(([name, mood, colors]) => ({ name, mood, colors: palette(colors.split(' ')) }))

export function samePalette(a: Palette, b: Palette): boolean {
  return ORDER.every((key) => a[key]?.toUpperCase() === b[key]?.toUpperCase())
}

/** Trois palettes construites autour d'une couleur principale. */
export function fromColor(primary: string): { name: string; hint: string; colors: Palette }[] {
  const [h, s, l] = toHsl(primary)
  const base = (secondary: string, accent: string): Palette => ({
    primary,
    secondary,
    accent,
    text: fromHsl(h, 25, 12),
    muted: fromHsl(h, 10, 38),
    band: fromHsl(h, 45, 96),
    title_band: fromHsl(h, 45, 91),
    link: primary,
  })
  return [
    {
      name: 'Monochrome',
      hint: 'Une seule teinte, plus claire ou plus foncée.',
      colors: base(fromHsl(h, s - 20, Math.min(l + 20, 62)), fromHsl(h, s, Math.max(l - 10, 18))),
    },
    {
      name: 'Complémentaire',
      hint: "L'accent pris à l'opposé du cercle des couleurs.",
      colors: base(fromHsl(h, s - 25, Math.min(l + 18, 60)), fromHsl(h + 180, 60, 38)),
    },
    {
      name: 'Voisines',
      hint: 'Deux teintes proches, de part et d’autre de la tienne.',
      colors: base(fromHsl(h - 30, s - 10, Math.min(l + 12, 55)), fromHsl(h + 35, 55, 38)),
    },
  ]
}

// ─── Couleur de chaque élément ───────────────────────────────────────────────

type BlockKey = keyof CVStyle['blocks']

export interface ElementColor {
  id: string
  label: string
  hint: string
  // La couleur de chaque réglage concerné (null : celle du texte).
  values: (style: CVStyle) => (string | null)[]
  apply: (style: CVStyle, value: string | null) => void
  // Libellé de « pas de couleur propre », si l'élément peut s'en passer.
  empty?: string
  // Le rôle que prend l'élément quand on choisit une palette, s'il n'a pas encore de couleur.
  suggested?: PaletteKey
}

const blocks = (keys: BlockKey[], empty = 'Couleur du texte', suggested?: PaletteKey) => ({
  values: (s: CVStyle) => keys.map((k) => (s.blocks[k] as TextStyle).color),
  apply: (s: CVStyle, v: string | null) => keys.forEach((k) => void ((s.blocks[k] as TextStyle).color = v)),
  empty,
  suggested,
})

export const ELEMENTS: ElementColor[] = [
  { id: 'name', label: 'Nom', hint: 'En haut du CV', ...blocks(['name']) },
  { id: 'headline', label: 'Titre sous le nom', hint: 'Le poste visé', ...blocks(['headline']) },
  { id: 'summary', label: 'Accroche', hint: 'Le court texte sous le titre', ...blocks(['summary']) },
  { id: 'contacts', label: 'Coordonnées', hint: 'Ville, téléphone, adresses', ...blocks(['contact_label', 'contact_strong', 'contact_value']) },
  { id: 'section_title', label: 'Titres de rubrique', hint: 'FORMATION, EXPÉRIENCE…', ...blocks(['section_title']) },
  {
    id: 'title_rule',
    label: 'Filets des titres',
    hint: 'Le trait sous chaque titre',
    values: (s) => [s.spacing.title_rule_color],
    apply: (s, v) => void (s.spacing.title_rule_color = v ?? 'primary'),
  },
  {
    id: 'title_band',
    label: 'Bandeau des titres',
    hint: 'Quand les titres sont en bandeau',
    values: (s) => [s.section_titles.band_color],
    apply: (s, v) => void (s.section_titles.band_color = v ?? 'primary'),
  },
  {
    id: 'entries',
    label: 'Intitulés',
    hint: 'Postes, diplômes, projets, groupes',
    ...blocks(['entry_title', 'experience_title', 'project_title', 'skill_label', 'language_name']),
  },
  { id: 'dates', label: 'Dates', hint: 'Juin 2026 – Août 2026', ...blocks(['date', 'date_in_place'], 'Couleur du texte', 'muted') },
  {
    id: 'places',
    label: 'Lieux et mentions',
    hint: 'Entreprise, ville, « en binôme »',
    ...blocks(['experience_place', 'experience_tag', 'project_tag'], 'Couleur du texte', 'muted'),
  },
  {
    id: 'bullets',
    label: 'Puces',
    hint: 'Le symbole devant chaque ligne',
    values: (s) => [s.lists.bullet_color],
    apply: (s, v) => void (s.lists.bullet_color = v),
    empty: 'Couleur du texte',
    suggested: 'accent',
  },
  {
    id: 'links',
    label: 'Liens',
    hint: 'GitHub, LinkedIn, site',
    values: (s) => [s.links.color],
    apply: (s, v) => void (s.links.color = v),
    empty: 'Comme le texte',
    suggested: 'link',
  },
  {
    id: 'band',
    label: 'Fond de colonne',
    hint: 'La colonne colorée',
    values: (s) => [s.band.color],
    apply: (s, v) => void (s.band.color = v ?? 'band'),
  },
  {
    id: 'header_rule',
    label: "Filet de l'en-tête",
    hint: 'Sous le nom et les coordonnées',
    values: (s) => [s.header.rule_color],
    apply: (s, v) => void (s.header.rule_color = v ?? 'primary'),
  },
  {
    id: 'frame',
    label: "Cadre de l'accroche",
    hint: 'Quand l’accroche est encadrée',
    values: (s) => [s.summary_frame.border_color],
    apply: (s, v) => void (s.summary_frame.border_color = v ?? 'primary'),
  },
  {
    id: 'photo',
    label: 'Bordure de la photo',
    hint: 'Quand la photo a une bordure',
    values: (s) => [s.photo.border_color],
    apply: (s, v) => void (s.photo.border_color = v ?? 'primary'),
  },
]

/** La valeur commune des réglages d'un élément, ou « mixed » s'ils diffèrent. */
export function elementValue(element: ElementColor, style: CVStyle): string | null | 'mixed' {
  const [first, ...rest] = element.values(style)
  return rest.every((value) => value === first) ? first : 'mixed'
}

/** Applique une palette ; les dates, lieux, puces et liens encore sans couleur prennent leur rôle. */
export function applyPalette(style: CVStyle, colors: Palette): void {
  ORDER.forEach((key) => void (style.palette[key] = colors[key]))
  for (const element of ELEMENTS) {
    if (element.suggested && element.values(style).every((value) => value === null)) element.apply(style, element.suggested)
  }
}

// ─── Lisibilité ──────────────────────────────────────────────────────────────

export interface Warning {
  text: string
  role: PaletteKey
  // La couleur corrigée du rôle, assez contrastée.
  fix: string
}

/** Les textes de la palette trop pâles sur leur fond (4,5:1 au moins), un avertissement par rôle. */
export function warnings(p: Palette): Warning[] {
  const checks: [PaletteKey, string, string][] = [
    ['text', 'FFFFFF', 'Le texte sur la page'],
    ['text', p.band, 'Le texte sur le fond de colonne'],
    ['muted', 'FFFFFF', 'Le texte discret sur la page'],
    ['muted', p.band, 'Le texte discret sur le fond de colonne'],
    ['primary', 'FFFFFF', 'La couleur principale sur la page'],
    ['primary', p.title_band, 'Les titres sur leur bandeau'],
    ['link', 'FFFFFF', 'Les liens sur la page'],
  ]
  const found: Warning[] = []
  for (const role of ORDER) {
    const mine = checks.filter(([r]) => r === role).map(([, background, label]) => ({ background, label, ratio: contrast(p[role], background) }))
    if (!mine.length) continue
    const worst = mine.reduce((a, b) => (b.ratio < a.ratio ? b : a))
    if (worst.ratio < 4.5)
      found.push({
        role,
        text: `${worst.label} : contraste ${ratioLabel(worst.ratio)}:1, peu lisible à l'écran et à l'impression (4,5:1 au moins).`,
        fix: readableOn(p[role], worst.background),
      })
  }
  return found
}
