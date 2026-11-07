import type { KeyProvider } from './types'

/** Les fournisseurs qui demandent une clé d'API (ou le code d'accès au relais), par leur nom affiché. */
export const KEY_NAMES: Record<KeyProvider, string> = { relais: 'Gemini de Yahya', gemini: 'Gemini', mistral: 'Mistral' }

/** Ce que la personne colle : le code d'accès que Yahya donne, ou une clé d'API. */
export const SECRET_LABELS: Record<KeyProvider, string> = { relais: "Code d'accès", gemini: "Clé d'API Gemini", mistral: "Clé d'API Mistral" }

export const SECRET_PLACEHOLDERS: Record<KeyProvider, string> = { relais: 'cvb-xxxx-xxxx-xxxx-xxxx', gemini: 'AIza…', mistral: 'Colle ta clé Mistral' }

export const keyed = (provider: string): provider is KeyProvider => provider === 'relais' || provider === 'gemini' || provider === 'mistral'
