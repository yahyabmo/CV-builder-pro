import type { CVContent } from './types'

/** Applique une coupe proposée par le serveur (« item:<section>:<n> », « bullet:<section>:<n>:<m> »). */
export function applyCut(content: CVContent, id: string): boolean {
  const [kind, sectionId, a, b] = id.split(':')
  const section = content.sections.find((s) => s.id === sectionId)
  if (!section) return false
  const index = Number(a)
  if (kind === 'item' && index < section.items.length) {
    section.items.splice(index, 1)
    return true
  }
  if (kind === 'bullet' && section.kind === 'experience' && section.items[index]) {
    const bullets = section.items[index].bullets
    if (Number(b) >= bullets.length) return false
    bullets.splice(Number(b), 1)
    return true
  }
  return false
}
