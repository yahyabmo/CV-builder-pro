import type { Change, Chip, Draft } from '@/lib/types'

export interface Decisions {
  accepted: Record<string, boolean>
  // Textes retouchés, par changement (une puce par ligne pour une expérience).
  texts: Record<string, string>
  // Compétences ajoutées ou retirées à la main : changement → compétence → gardée.
  chips: Record<string, Record<string, boolean>>
  // Traductions retouchées, par chemin.
  translation: Record<string, string>
}

const SHOWN = new Set<Chip['state']>(['kept', 'added'])

/** Au départ, tout est accepté sauf les phrases qui ont un terme à confirmer. */
export function initialDecisions(draft: Draft): Decisions {
  return {
    accepted: Object.fromEntries(draft.changes.map((c) => [c.id, !(c.pending.length > 0 && c.group !== 'Compétences')])),
    texts: {},
    chips: {},
    translation: {},
  }
}

/** Une compétence est-elle dans le groupe ? Les « à confirmer » ne le sont qu'après un clic. */
export function chipShown(decisions: Decisions, change: Change, chip: Chip): boolean {
  return decisions.chips[change.id]?.[chip.text] ?? SHOWN.has(chip.state)
}

/** Le texte final d'un changement avec les choix en cours. */
export function changeText(change: Change, decisions: Decisions): string {
  if (change.chips.length > 0 && change.kind !== 'remove') {
    const shown = change.chips.filter((chip) => chipShown(decisions, change, chip)).map((chip) => chip.text)
    return shown.length ? `${shown.join(', ')}.` : ''
  }
  return decisions.texts[change.id] ?? change.after
}

/** Les changements acceptés, avec leur texte final, tels que l'API les attend. */
export function acceptedTexts(draft: Draft, decisions: Decisions): Record<string, string> {
  return Object.fromEntries(draft.changes.filter((c) => decisions.accepted[c.id]).map((c) => [c.id, changeText(c, decisions)]))
}

/** Les termes confirmés : compétences « à confirmer » cochées, termes des phrases acceptées. */
export function confirmedTerms(draft: Draft, decisions: Decisions): string[] {
  const out = new Set<string>()
  for (const change of draft.changes) {
    if (!decisions.accepted[change.id]) continue
    if (change.chips.length > 0) {
      change.chips.filter((chip) => chip.state === 'pending' && chipShown(decisions, change, chip)).forEach((chip) => out.add(chip.text))
    } else {
      change.pending.forEach((term) => out.add(term))
    }
  }
  return [...out]
}

/** Ce qui reste à confirmer : compétences en attente, phrases décochées à cause d'un terme. */
export function pendingCount(draft: Draft, decisions: Decisions): number {
  return draft.changes.reduce((n, change) => {
    if (change.chips.length > 0) return n + change.chips.filter((chip) => chip.state === 'pending' && !chipShown(decisions, change, chip)).length
    return n + (change.pending.length > 0 && !decisions.accepted[change.id] ? 1 : 0)
  }, 0)
}

/** Après une relance : les choix déjà faits, repris là où ils s'appliquent encore. */
export function carryDecisions(old: Draft, previous: Decisions, next: Draft): Decisions {
  const fresh = initialDecisions(next)
  const before = new Map(old.changes.map((c) => [c.id, c]))
  // Une compétence ajoutée ou retirée à la main l'est encore, quel que soit son groupe.
  const chipChoices = new Map<string, boolean>()
  for (const choices of Object.values(previous.chips)) for (const [text, shown] of Object.entries(choices)) chipChoices.set(text, shown)
  for (const change of next.changes) {
    const prev = before.get(change.id)
    if (prev && prev.after === change.after) {
      fresh.accepted[change.id] = previous.accepted[change.id] ?? fresh.accepted[change.id]
      if (previous.texts[change.id] != null) fresh.texts[change.id] = previous.texts[change.id]
    }
    const carried = change.chips.filter((chip) => chipChoices.has(chip.text))
    if (carried.length) fresh.chips[change.id] = Object.fromEntries(carried.map((chip) => [chip.text, chipChoices.get(chip.text) as boolean]))
  }
  fresh.translation = Object.fromEntries(Object.entries(previous.translation).filter(([path]) => path in next.translation))
  return fresh
}
