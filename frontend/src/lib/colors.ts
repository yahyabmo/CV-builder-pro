// Couleurs en hexadécimal sans « # » (« 2E43A3 »), comme dans style.json.

export function toRgb(hex: string): [number, number, number] {
  return [parseInt(hex.slice(0, 2), 16), parseInt(hex.slice(2, 4), 16), parseInt(hex.slice(4, 6), 16)]
}

export function fromRgb(r: number, g: number, b: number): string {
  return [r, g, b]
    .map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0'))
    .join('')
    .toUpperCase()
}

/** Teinte (0–360), saturation et luminosité (0–100). */
export function toHsl(hex: string): [number, number, number] {
  const [r, g, b] = toRgb(hex).map((v) => v / 255)
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  const light = (max + min) / 2
  if (max === min) return [0, 0, light * 100]
  const d = max - min
  const sat = light > 0.5 ? d / (2 - max - min) : d / (max + min)
  const hue = max === r ? (g - b) / d + (g < b ? 6 : 0) : max === g ? (b - r) / d + 2 : (r - g) / d + 4
  return [hue * 60, sat * 100, light * 100]
}

export function fromHsl(h: number, s: number, l: number): string {
  const hue = ((h % 360) + 360) % 360
  const sat = Math.max(0, Math.min(100, s)) / 100
  const light = Math.max(0, Math.min(100, l)) / 100
  const c = (1 - Math.abs(2 * light - 1)) * sat
  const x = c * (1 - Math.abs(((hue / 60) % 2) - 1))
  const m = light - c / 2
  const [r, g, b] =
    hue < 60 ? [c, x, 0] : hue < 120 ? [x, c, 0] : hue < 180 ? [0, c, x] : hue < 240 ? [0, x, c] : hue < 300 ? [x, 0, c] : [c, 0, x]
  return fromRgb((r + m) * 255, (g + m) * 255, (b + m) * 255)
}

function luminance(hex: string): number {
  const [r, g, b] = toRgb(hex).map((v) => {
    const c = v / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

/** Le contraste entre deux couleurs, de 1 (aucun) à 21 (noir sur blanc). */
export function contrast(a: string, b: string): number {
  const x = luminance(a)
  const y = luminance(b)
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05)
}

/** La couleur assombrie (ou éclaircie sur fond sombre) jusqu'à atteindre le contraste voulu. */
export function readableOn(color: string, background: string, ratio = 4.5): string {
  const [h, s, l] = toHsl(color)
  const darker = luminance(background) > 0.18
  let light = l
  let found = color
  while (contrast(found, background) < ratio && light > 0 && light < 100) {
    light += darker ? -2 : 2
    found = fromHsl(h, s, light)
  }
  return found
}

/** « 3,1 » : un contraste à la française, une décimale. */
export function ratioLabel(value: number): string {
  return value.toFixed(1).replace('.', ',')
}
