import type { ApplicationStatus, CVSummary } from './types'

export const STATUS_ORDER: ApplicationStatus[] = ['todo', 'sent', 'interview', 'offer', 'refused']

export const STATUS: Record<ApplicationStatus, { label: string; plural: string; pill: string; dot: string }> = {
  todo: { label: 'À envoyer', plural: 'À envoyer', pill: 'bg-status-todo-soft text-status-todo', dot: 'bg-status-todo' },
  sent: { label: 'Envoyée', plural: 'Envoyées', pill: 'bg-status-sent-soft text-status-sent', dot: 'bg-status-sent' },
  interview: { label: 'Entretien', plural: 'Entretien', pill: 'bg-status-interview-soft text-status-interview', dot: 'bg-status-interview' },
  offer: { label: 'Offre', plural: 'Offre', pill: 'bg-status-offer-soft text-status-offer', dot: 'bg-status-offer' },
  refused: { label: 'Refus', plural: 'Refus', pill: 'bg-status-refused-soft text-status-refused', dot: 'bg-status-refused' },
}

const TINTS = [
  'bg-status-sent-soft text-status-sent',
  'bg-status-interview-soft text-status-interview',
  'bg-status-offer-soft text-status-offer',
  'bg-status-violet-soft text-status-violet',
  'bg-status-teal-soft text-status-teal',
]

const shortDate = new Intl.DateTimeFormat('fr', { day: 'numeric', month: 'short' })
const DAY = 86_400_000

/** « 2026-10-20 » ou un instant ISO → « 20 oct. ». */
export function dayLabel(value: string): string {
  return shortDate.format(new Date(value.length === 10 ? `${value}T00:00` : value))
}

/** Aujourd'hui au format AAAA-MM-JJ, à l'heure locale. */
export function today(): string {
  const now = new Date()
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 10)
}

function daysBetween(from: string, to: string): number {
  return Math.round((new Date(`${to}T00:00`).getTime() - new Date(`${from}T00:00`).getTime()) / DAY)
}

/** L'entreprise de l'offre, ou le nom du CV s'il ne vise aucune offre. */
export function company(cv: CVSummary): string {
  return cv.meta.company?.trim() || cv.meta.name
}

export function position(cv: CVSummary): string {
  return cv.meta.position?.trim() || cv.meta.name
}

const COUNTRIES = /^(france|maroc|belgique|suisse|luxembourg|canada|allemagne|espagne|royaume-uni)$/i

/** La ville d'une adresse : « …, 75003 Paris » → « Paris » ; « Talence, France » → « Talence ». */
export function city(location: string): string {
  const postal = location.match(/\b\d{5}\s+([\p{L}' -]+)/u)
  if (postal) return postal[1].trim()
  const parts = location.split(',').map((part) => part.trim()).filter(Boolean)
  if (parts.length > 1 && COUNTRIES.test(parts[parts.length - 1])) return parts[0]
  return location.trim()
}

export function where(cv: CVSummary): string {
  if (!cv.meta.company) return 'Sans offre visée'
  return [city(cv.location), cv.contract].filter(Boolean).join(' · ') || 'Offre ciblée'
}

/** La pastille de l'entreprise : sa première lettre, sur une teinte stable. */
export function monogram(cv: CVSummary): { letter: string; tint: string } {
  const name = company(cv)
  let hash = 0
  for (const char of name.toLowerCase()) hash = (hash * 31 + char.charCodeAt(0)) >>> 0
  const letter = name.match(/\p{L}|\d/u)?.[0]?.toUpperCase() ?? '?'
  return { letter, tint: TINTS[hash % TINTS.length] }
}

/** La prochaine chose à savoir sur la candidature, en une ligne. */
export function nextStep(cv: CVSummary, now = today()): { text: string; late: boolean } {
  const app = cv.meta.application
  const last = app.history[0]
  switch (app.status) {
    case 'todo':
      return { text: `CV prêt le ${dayLabel(cv.meta.created_at)} · pas encore envoyée`, late: false }
    case 'sent':
      if (cv.due && app.follow_up_on) return { text: lateText(app.follow_up_on, now), late: true }
      return {
        text: [app.sent_on && `Envoyée le ${dayLabel(app.sent_on)}`, app.follow_up_on && `relance le ${dayLabel(app.follow_up_on)}`]
          .filter(Boolean)
          .join(' · '),
        late: false,
      }
    default:
      return { text: last ? `${last.text} le ${dayLabel(last.on)}` : STATUS[app.status].label, late: false }
  }
}

/** « Relance prévue le 30 oct., 4 jours de retard ». */
export function lateText(followUpOn: string, now = today()): string {
  const late = daysBetween(followUpOn, now)
  if (late <= 0) return "Relance prévue aujourd'hui"
  return `Relance prévue le ${dayLabel(followUpOn)}, ${late} jour${late > 1 ? 's' : ''} de retard`
}
