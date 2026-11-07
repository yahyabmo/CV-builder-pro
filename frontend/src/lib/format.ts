const relative = new Intl.RelativeTimeFormat('fr', { numeric: 'auto' })

/** « il y a 3 minutes », « hier »… */
export function sinceNow(iso: string): string {
  const seconds = (new Date(iso).getTime() - Date.now()) / 1000
  const steps: [Intl.RelativeTimeFormatUnit, number][] = [
    ['year', 31536000],
    ['month', 2592000],
    ['week', 604800],
    ['day', 86400],
    ['hour', 3600],
    ['minute', 60],
  ]
  for (const [unit, size] of steps) {
    if (Math.abs(seconds) >= size) return relative.format(Math.round(seconds / size), unit)
  }
  return "à l'instant"
}

// Mots qui ne disent rien du poste (même liste que le serveur, cv_store._STOP).
const STOP = new Set(
  'stage stages stagiaire internship intern ingenieur ingenieure engineer h f hf fh m w x de du des la le les l d et en pour par a au aux un une avec sur dans the of for and in to with pfe fin etudes cdi cdd alternance alternant apprenti master m2 junior senior'.split(' '),
)

/** 1 à 3 mots tirés d'un texte, pour un nom de fichier : « Agent IA analyste » → « agent-ia-analyste ». */
export function shortLabel(text: string): string {
  const plain = text.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
  return (plain.match(/[a-z0-9]+/g) ?? []).filter((w) => !STOP.has(w) && !/^\d+$/.test(w)).slice(0, 3).join('-')
}
