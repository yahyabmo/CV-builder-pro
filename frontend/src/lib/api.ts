import type {
  ApplyBaseResult,
  ImportReading,
  ImportResult,
  ApplicationPatch,
  AISettings,
  ApplyResult,
  AtsReport,
  CompileResult,
  ConnectionTest,
  CVContent,
  CVDetail,
  CVStyle,
  CVSummary,
  Draft,
  FontInfo,
  BulkResult,
  Coverage,
  FillResult,
  Library,
  LibraryExperience,
  LibraryProject,
  LetterContent,
  LetterState,
  LibrarySkill,
  ProjectDraft,
  RuleKind,
  SkillLevel,
  OfferInfo,
  PageLocation,
  SavedIdeas,
  StyleFinding,
  SettingsInfo,
  WelcomeState,
  KeyProvider,
  KeyResult,
  Machine,
  SourceInfo,
  SourceResult,
  TermsResult,
  TargetEvent,
  TargetRequest,
  Theme,
  Me,
  SignatureInfo,
  SignatureSize,
  AdminPeople,
  AdminPersonDetail,
} from './types'
import { intentFields, type WelcomeIntent } from './welcome-intent'

/** Évènement de fenêtre : la personne connectée n'a plus accès (détail : son e-mail). */
export const ACCESS_PAUSED = 'cvb:access-paused'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

// Un message lisible depuis une réponse d'erreur FastAPI (texte ou liste de
// validation Pydantic).
function readable(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { loc?: unknown[]; msg?: string }
    const where = Array.isArray(first.loc) ? first.loc.slice(1).join(' › ') : ''
    return `Contenu invalide${where ? ` (${where})` : ''} : ${first.msg ?? ''}`
  }
  return 'Erreur inattendue du serveur'
}

async function send(path: string, init?: RequestInit): Promise<Response> {
  let response: Response
  try {
    response = await fetch(path, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
  } catch (error) {
    if (init?.signal?.aborted) throw error
    throw new ApiError(0, 'Le serveur ne répond pas. Lance « make start » dans le dossier du projet.')
  }
  if (!response.ok) {
    let detail: unknown = response.statusText
    let body: { detail?: unknown; code?: string; email?: string } = {}
    try {
      body = (await response.json()) as typeof body
      detail = body.detail
    } catch {
      /* réponse sans JSON */
    }
    // En ligne, l'administrateur a retiré l'accès : l'appli montre l'écran « accès en pause ».
    // La demande reste sans réponse : l'écran remplace l'appli, sans messages d'erreur derrière.
    if (response.status === 403 && body.code === 'paused') {
      window.dispatchEvent(new CustomEvent<string>(ACCESS_PAUSED, { detail: body.email ?? '' }))
      return await new Promise<Response>(() => undefined)
    }
    // En ligne, la connexion Cloudflare a expiré : recharger la page ramène à la connexion.
    if (response.status === 401) throw new ApiError(401, 'Ta connexion a expiré : recharge la page pour te reconnecter.')
    throw new ApiError(response.status, readable(detail))
  }
  return response
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  return (await (await send(path, init)).json()) as T
}

/** Un flux d'évènements (text/event-stream) en réponse à un POST : un rappel par évènement. */
async function stream<E>(path: string, body: unknown, onEvent: (event: E) => void, signal?: AbortSignal) {
  const response = await send(path, { method: 'POST', body: JSON.stringify(body), signal })
  if (!response.body) throw new ApiError(0, 'Réponse vide du serveur')
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += value
    let end = buffer.indexOf('\n\n')
    while (end >= 0) {
      const data = buffer
        .slice(0, end)
        .split('\n')
        .filter((line) => line.startsWith('data: '))
        .map((line) => line.slice(6))
        .join('\n')
      buffer = buffer.slice(end + 2)
      if (data) onEvent(JSON.parse(data) as E)
      end = buffer.indexOf('\n\n')
    }
  }
}

export const api = {
  listCVs: () => request<CVSummary[]>('/api/cvs'),
  getCV: (slug: string) => request<CVDetail>(`/api/cvs/${slug}`),
  createCV: (name: string, source: string, kind: 'cv' | 'base' = 'cv') =>
    request<CVSummary>('/api/cvs', { method: 'POST', body: JSON.stringify({ name, source, kind }) }),
  renameCV: (slug: string, name: string, label?: string) =>
    request<CVSummary>(`/api/cvs/${slug}`, { method: 'PATCH', body: JSON.stringify({ name, label }) }),
  deleteCV: (slug: string) => request<{ trash: string }>(`/api/cvs/${slug}`, { method: 'DELETE' }),
  updateApplication: (slug: string, patch: ApplicationPatch) =>
    request<CVSummary>(`/api/cvs/${slug}/application`, { method: 'PATCH', body: JSON.stringify(patch) }),
  thumbnailUrl: (slug: string, version: number | null) =>
    `/api/cvs/${slug}/thumbnail${version ? `?v=${version}` : ''}`,
  texUrl: (slug: string) => `/api/cvs/${slug}/tex`,
  getLibrary: () => request<Library>('/api/library'),
  saveProjects: (projects: LibraryProject[]) =>
    request<Library>('/api/library/projects', { method: 'PUT', body: JSON.stringify(projects) }),
  saveSkills: (skills: LibrarySkill[]) =>
    request<Library>('/api/library/skills', { method: 'PUT', body: JSON.stringify(skills) }),
  saveExperiences: (experiences: LibraryExperience[]) =>
    request<Library>('/api/library/experiences', { method: 'PUT', body: JSON.stringify(experiences) }),
  fillLibrary: () => request<FillResult>('/api/library/fill', { method: 'POST' }),
  skillGroup: (term: string, groups: string[]) =>
    request<{ group: string | null; exists: boolean }>('/api/library/skills/group', { method: 'POST', body: JSON.stringify({ term, groups }) }),
  addSkills: (text: string, options: { category?: string; level?: SkillLevel | null; evidence?: string; source?: 'manuel' | 'offre' } = {}) =>
    request<BulkResult>('/api/library/skills/bulk', { method: 'POST', body: JSON.stringify({ text, ...options }) }),
  draftProject: (id: string) => request<ProjectDraft>(`/api/library/projects/${id}/draft`, { method: 'POST' }),
  saveContent: (slug: string, content: CVContent) =>
    request<CVSummary>(`/api/cvs/${slug}/content`, {
      method: 'PUT',
      body: JSON.stringify(content),
    }),
  saveStyle: (slug: string, style: CVStyle) =>
    request<CVSummary>(`/api/cvs/${slug}/style`, { method: 'PUT', body: JSON.stringify(style) }),
  uploadPhoto: async (slug: string, file: Blob) => {
    const form = new FormData()
    form.append('file', file, 'photo.jpg')
    // Pas d'en-tête Content-Type : le navigateur pose la frontière du formulaire.
    const response = await fetch(`/api/cvs/${slug}/photo`, { method: 'POST', body: form })
    if (!response.ok) {
      const body = (await response.json().catch(() => ({}))) as { detail?: unknown }
      throw new ApiError(response.status, readable(body.detail))
    }
    return (await response.json()) as { photo: string; version: number }
  },
  signature: () => request<SignatureInfo>('/api/signature'),
  signatureImageUrl: (version: number | null) => `/api/signature/image?v=${version ?? 0}`,
  uploadSignature: async (file: Blob, name: string) => {
    const form = new FormData()
    form.append('file', file, name)
    // Pas d'en-tête Content-Type : le navigateur pose la frontière du formulaire.
    const response = await fetch('/api/signature', { method: 'PUT', body: form })
    if (!response.ok) {
      const body = (await response.json().catch(() => ({}))) as { detail?: unknown }
      throw new ApiError(response.status, readable(body.detail))
    }
    return (await response.json()) as SignatureInfo
  },
  setSignatureSize: (size: SignatureSize) => request<SignatureInfo>('/api/signature', { method: 'PATCH', body: JSON.stringify({ size }) }),
  deleteSignature: () => request<SignatureInfo>('/api/signature', { method: 'DELETE' }),
  listFonts: () => request<FontInfo[]>('/api/fonts'),
  fontUrl: (id: string, style: 'regular' | 'bold' | 'italic' | 'bold_italic' = 'regular') =>
    `/api/fonts/${id}/${style}`,
  listThemes: () => request<Theme[]>('/api/themes'),
  createTheme: (name: string, style: CVStyle) =>
    request<Theme>('/api/themes', { method: 'POST', body: JSON.stringify({ name, style }) }),
  deleteTheme: (slug: string) => request<{ deleted: boolean }>(`/api/themes/${slug}`, { method: 'DELETE' }),
  compile: (slug: string) =>
    request<CompileResult>(`/api/cvs/${slug}/compile`, { method: 'POST' }),
  pdfUrl: (slug: string, version: number | null) =>
    `/api/cvs/${slug}/pdf${version ? `?v=${version}` : ''}`,
  photoUrl: (slug: string, version?: number | string) =>
    `/api/cvs/${slug}/photo${version ? `?v=${version}` : ''}`,
  rules: (kind: RuleKind) => request<{ rules: string[] }>(`/api/rules/${kind}`),
  saveRules: (kind: RuleKind, rules: string[]) =>
    request<{ rules: string[] }>(`/api/rules/${kind}`, { method: 'PUT', body: JSON.stringify({ rules }) }),
  letter: (slug: string) => request<LetterState>(`/api/cvs/${slug}/letter`),
  generateLetter: (slug: string, why: string, detail: string) =>
    request<{ state: LetterState; compile: CompileResult }>(`/api/cvs/${slug}/letter/generate`, {
      method: 'POST',
      body: JSON.stringify({ why, detail }),
    }),
  saveLetter: (slug: string, letter: LetterContent) =>
    request<LetterState>(`/api/cvs/${slug}/letter`, { method: 'PUT', body: JSON.stringify(letter) }),
  compileLetter: (slug: string) => request<CompileResult>(`/api/cvs/${slug}/letter/compile`, { method: 'POST' }),
  letterPdfUrl: (slug: string, version: number | null) => `/api/cvs/${slug}/letter/pdf${version ? `?v=${version}` : ''}`,
  letterTexUrl: (slug: string) => `/api/cvs/${slug}/letter/tex`,
  letterText: (slug: string) => request<{ text: string }>(`/api/cvs/${slug}/letter/text`),
  letterSource: (slug: string) => request<SourceInfo>(`/api/cvs/${slug}/letter/source`),
  saveLetterSource: (slug: string, tex: string) =>
    request<SourceResult>(`/api/cvs/${slug}/letter/source`, { method: 'PUT', body: JSON.stringify({ tex }) }),
  letterToVisual: (slug: string) => request<SourceResult>(`/api/cvs/${slug}/letter/visual`, { method: 'POST' }),
  getSource: (slug: string) => request<SourceInfo>(`/api/cvs/${slug}/source`),
  saveSource: (slug: string, tex: string) =>
    request<SourceResult>(`/api/cvs/${slug}/source`, { method: 'PUT', body: JSON.stringify({ tex }) }),
  backToVisual: (slug: string) => request<SourceResult>(`/api/cvs/${slug}/visual`, { method: 'POST' }),
  // L'élément du contenu sous un point de l'aperçu (en points depuis le haut gauche).
  locate: (slug: string, x: number, y: number) =>
    request<PageLocation | null>(`/api/cvs/${slug}/locate?x=${x.toFixed(1)}&y=${y.toFixed(1)}`),
  ats: (slug: string) => request<AtsReport>(`/api/cvs/${slug}/ats`),
  atsTerms: (slug: string, terms: string[]) =>
    request<TermsResult>(`/api/cvs/${slug}/ats/terms`, { method: 'POST', body: JSON.stringify({ terms }) }),
  cutCV: (slug: string, id: string) =>
    request<CompileResult>(`/api/cvs/${slug}/cut`, { method: 'POST', body: JSON.stringify({ id }) }),
  target: (body: TargetRequest, onEvent: (event: TargetEvent) => void, signal?: AbortSignal) =>
    stream<TargetEvent>('/api/target', body, onEvent, signal),
  getDraft: (id: string) => request<Draft>(`/api/target/drafts/${id}`),
  rerun: (id: string, onEvent: (event: TargetEvent) => void, signal?: AbortSignal) =>
    stream<TargetEvent>(`/api/target/drafts/${id}/rerun`, {}, onEvent, signal),
  scoreDraft: (id: string, accepted: Record<string, string>, translationEdits: Record<string, string>, signal?: AbortSignal) =>
    request<Coverage>(`/api/target/drafts/${id}/score`, {
      method: 'POST',
      body: JSON.stringify({ accepted, translation_edits: translationEdits }),
      signal,
    }),
  applyDraft: (
    id: string,
    name: string,
    accepted: Record<string, string>,
    translationEdits: Record<string, string>,
    confirmed: string[],
  ) =>
    request<ApplyResult>(`/api/target/drafts/${id}/apply`, {
      method: 'POST',
      body: JSON.stringify({ name, accepted, translation_edits: translationEdits, confirmed }),
    }),
  getOffer: (slug: string) => request<OfferInfo>(`/api/target/offer/${slug}`),
  getSettings: () => request<SettingsInfo>('/api/settings'),
  me: () => request<Me>('/api/me'),
  exportUrl: '/api/export',
  adminPeople: () => request<AdminPeople>('/api/admin/people'),
  adminInvite: (email: string) => request<AdminPeople>('/api/admin/people', { method: 'POST', body: JSON.stringify({ email }) }),
  adminSync: () => request<AdminPeople>('/api/admin/people/sync', { method: 'POST' }),
  adminRemove: (email: string) => request<AdminPeople>(`/api/admin/people/${encodeURIComponent(email)}`, { method: 'DELETE' }),
  adminErase: (email: string) => request<AdminPeople>(`/api/admin/people/${encodeURIComponent(email)}/data`, { method: 'DELETE' }),
  adminPerson: (email: string) => request<AdminPersonDetail>(`/api/admin/people/${encodeURIComponent(email)}`),
  adminPdfUrl: (email: string, slug: string, version: number | null) =>
    `/api/admin/people/${encodeURIComponent(email)}/cvs/${slug}/pdf?v=${version ?? 0}`,
  adminExportUrl: (email: string) => `/api/admin/people/${encodeURIComponent(email)}/export`,
  demoOffer: () => request<{ text: string }>('/api/target/demo-offer'),
  welcome: () => request<WelcomeState>('/api/welcome'),
  dismissWelcome: () => request<WelcomeState>('/api/welcome/dismiss', { method: 'POST' }),
  setupDone: () => request<WelcomeState>('/api/welcome/setup', { method: 'POST' }),
  blankCV: () => request<CVContent>('/api/welcome/blank'),
  demoPdfUrl: '/api/welcome/demo-pdf',
  uploadImport: async (file: Blob, name: string) => {
    const form = new FormData()
    form.append('file', file, name)
    // Pas d'en-tête Content-Type : le navigateur pose la frontière du formulaire.
    let response: Response
    try {
      response = await fetch('/api/welcome/import', { method: 'POST', body: form })
    } catch {
      throw new ApiError(0, 'Le serveur ne répond pas. Lance « make start » dans le dossier du projet.')
    }
    if (!response.ok) {
      const body = (await response.json().catch(() => ({}))) as { detail?: unknown }
      throw new ApiError(response.status, readable(body.detail))
    }
    return (await response.json()) as ImportReading
  },
  readImport: (id: string) => request<ImportResult>(`/api/welcome/import/${id}/read`, { method: 'POST' }),
  getImport: (id: string) => request<ImportResult>(`/api/welcome/import/${id}`),
  importSourceUrl: (id: string) => `/api/welcome/import/${id}/source`,
  importPhotoUrl: (id: string) => `/api/welcome/import/${id}/photo`,
  // Les idées de projet d'un CV ciblé : gardées, ou trois nouvelles (une requête).
  projectIdeas: (slug: string) => request<SavedIdeas>(`/api/cvs/${slug}/project-ideas`),
  proposeProjectIdeas: (slug: string) => request<SavedIdeas>(`/api/cvs/${slug}/project-ideas`, { method: 'POST' }),
  projectBriefUrl: (slug: string, index: number) => `/api/cvs/${slug}/project-ideas/${index}/brief`,
  // Le style repéré dans le PDF : police, couleurs, colonnes, titres…
  importStyle: (id: string) => request<{ findings: StyleFinding[] }>(`/api/welcome/import/${id}/style`),
  // keep : les éléments du style du PDF à reprendre ; null, le style de l'appli.
  previewImport: (id: string, content: CVContent, keep: string[] | null = null) =>
    request<CompileResult>(`/api/welcome/import/${id}/preview`, { method: 'POST', body: JSON.stringify({ content, keep }) }),
  importPreviewUrl: (id: string, version: number) => `/api/welcome/import/${id}/preview.pdf?v=${version}`,
  applyBase: (content: CVContent, importId?: string, keepPhoto = true, keep: string[] | null = null, intent: WelcomeIntent | null = null) =>
    request<ApplyBaseResult>('/api/welcome/apply', {
      method: 'POST',
      body: JSON.stringify({ content, import_id: importId ?? null, keep_photo: keepPhoto, keep, ...intentFields(intent) }),
    }),
  saveSettings: (ai: AISettings) =>
    request<SettingsInfo>('/api/settings', { method: 'PUT', body: JSON.stringify(ai) }),
  testConnection: () => request<ConnectionTest>('/api/settings/test', { method: 'POST' }),
  saveKey: (provider: KeyProvider, key: string) =>
    request<KeyResult>(`/api/settings/keys/${provider}`, { method: 'PUT', body: JSON.stringify({ key }) }),
  deleteKey: (provider: KeyProvider) => request<SettingsInfo>(`/api/settings/keys/${provider}`, { method: 'DELETE' }),
  checkMachine: () => request<Machine>('/api/system/check'),
}
