import type { PageLocation } from './types'

/** Une demande d'aller à un champ de l'éditeur (clic sur l'aperçu, sommaire, mot-clé ajouté). */
export interface FocusRequest {
  location: PageLocation
  nonce: number
}

/** L'emplacement d'une rubrique (ou d'un de ses éléments) ; sans rubrique, l'en-tête. */
export function at(section: string | null, item: number | null = null): PageLocation {
  return { area: section ? 'section' : 'header', section, item, bullet: null, line: null, box: null }
}
