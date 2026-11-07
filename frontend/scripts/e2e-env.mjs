// Où tournent les essais de l'interface : un backend et une interface à part
// (make e2e), sur une copie jetable du CV fictif, jamais sur tes données.

export const API = process.env.E2E_API ?? 'http://127.0.0.1:8001'
export const APP = process.env.E2E_APP ?? 'http://127.0.0.1:5174'
// Dossiers de données et de réglages du backend d'essai, vus depuis frontend/.
export const DATA = process.env.E2E_DATA ?? '../build/e2e-data'
export const LOCAL = process.env.E2E_LOCAL ?? '../build/e2e-local'
