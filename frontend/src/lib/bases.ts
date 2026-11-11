import type { CVSummary } from './types'

// Le dernier CV ouvert (App.tsx l'écrit à chaque ouverture).
export const LAST_OPENED = 'cv-builder.selected'

/** Les CV classiques : la première version d'abord, puis les autres par nom. */
export function baseCVs(cvs: CVSummary[]): CVSummary[] {
  const bases = cvs.filter((cv) => cv.meta.kind === 'base')
  return [...bases].sort((a, b) => (a.slug === 'base' ? -1 : b.slug === 'base' ? 1 : a.meta.name.localeCompare(b.meta.name, 'fr')))
}

/** Le CV classique proposé pour cibler une offre : le dernier ouvert, sinon la première version. */
export function lastBase(cvs: CVSummary[] | null): string {
  try {
    const last = localStorage.getItem(LAST_OPENED)
    if (last && cvs?.some((cv) => cv.slug === last && cv.meta.kind === 'base')) return last
  } catch {
    /* stockage indisponible */
  }
  return 'base'
}
