// Miroir des modèles Pydantic du backend (app/models/*.py).

export type Column = 'left' | 'right'

export interface ContactItem {
  text: string
  label?: string | null
  url?: string | null
  bold?: boolean
}

export interface Header {
  name: string
  headline: string
  summary: string
  photo?: string | null
  contact_lines: ContactItem[][]
}

interface SectionBase {
  id: string
  title: string
  column: Column
  visible: boolean
}

export interface EducationItem {
  title: string
  place: string
  dates: string
  description: string
}

export interface SkillGroup {
  label: string
  text: string
}

export interface GridItem {
  text: string
  wide?: boolean
}

export interface Language {
  name: string
  level: string
}

export interface ExperienceItem {
  title: string
  tag: string
  place: string
  dates: string
  bullets: string[]
}

export interface ProjectItem {
  title: string
  tag: string
  date: string
  description: string
  link?: string | null
  library_id?: string | null
}

export type Section =
  | (SectionBase & { kind: 'education'; items: EducationItem[] })
  | (SectionBase & { kind: 'skills'; items: SkillGroup[] })
  | (SectionBase & { kind: 'grid'; items: GridItem[] })
  | (SectionBase & { kind: 'languages'; items: Language[] })
  | (SectionBase & { kind: 'bullets'; items: string[] })
  | (SectionBase & { kind: 'experience'; layout: 'detailed' | 'compact'; items: ExperienceItem[] })
  | (SectionBase & { kind: 'projects'; items: ProjectItem[] })

export type SectionKind = Section['kind']

export interface CVContent {
  schema_version: number
  language: 'fr' | 'en'
  header: Header
  sections: Section[]
}

// ─── Suivi d'une candidature (app/models/application.py) ─────────────────────

export type ApplicationStatus = 'todo' | 'sent' | 'interview' | 'offer' | 'refused'

export interface ApplicationEvent {
  on: string
  text: string
}

export interface Application {
  status: ApplicationStatus
  // Dates au format AAAA-MM-JJ.
  sent_on: string | null
  follow_up_on: string | null
  contact: string
  contact_email: string
  notes: string
  // Du plus récent au plus ancien.
  history: ApplicationEvent[]
}

export interface ApplicationPatch {
  status?: ApplicationStatus
  sent_on?: string | null
  follow_up_on?: string | null
  contact?: string
  contact_email?: string
  notes?: string
  offer_url?: string
  // « Relancée aujourd'hui » : la relance est notée, la suivante proposée dix jours après.
  followed_up?: boolean
}

export interface CVMeta {
  name: string
  kind: 'base' | 'cv'
  mode: CVMode
  source: string | null
  company?: string | null
  position?: string | null
  offer_url?: string | null
  // 1 à 3 mots de l'offre pour le nom du fichier, choisis à la main.
  label?: string | null
  // Couverture des mots-clés de l'offre (sur 100), mesurée sur le PDF.
  score?: number | null
  created_at: string
  updated_at: string
  pages: number | null
  application: Application
}

export interface CVSummary {
  slug: string
  meta: CVMeta
  pdf_version: number | null
  // Nom du fichier téléchargé, sans extension : « camille_laurent_agent-ia ».
  file_stem: string
  // Les mots de l'offre dans ce nom, vide s'il n'y en a pas.
  file_label: string
  // L'offre visée : lieu et contrat, tirés de son analyse.
  location: string
  contract: string
  // Une relance à faire aujourd'hui.
  due: boolean
}

export interface CVDetail extends CVSummary {
  content: CVContent
  style: CVStyle
}

export interface LatexError {
  message: string
  line: number | null
  context: string
}

export interface CompileResult {
  ok: boolean
  superseded: boolean
  pages: number | null
  seconds: number
  overflow_pt: number
  pdf_version: number | null
  errors: LatexError[]
  // Coupes proposées quand une colonne déborde.
  cuts: Cut[]
}

// ─── Code LaTeX et vérification ATS ──────────────────────────────────────────

export type CVMode = 'visual' | 'manual'

export interface SourceInfo {
  tex: string
  mode: CVMode
}

export interface SourceResult {
  mode: CVMode
  compile: CompileResult
}

export interface AtsCheck {
  id: string
  label: string
  status: 'ok' | 'warn' | 'fail'
  detail: string
}

export interface AtsReport {
  checks: AtsCheck[]
  words: { total: number; found: number; missing: string[] }
  text: string
}

export interface TermsResult {
  present: string[]
  absent: string[]
}

export interface Cut {
  id: string
  column: Column
  label: string
  detail: string
}

// ─── Ciblage d'une offre (miroir de app/ai/*.py) ─────────────────────────────

export interface Keyword {
  term: string
  importance: 1 | 2 | 3
  category: string
}

export interface OfferAnalysis {
  is_job_offer: boolean
  job_title: string
  company: string
  location: string
  contract: string
  offer_language: 'fr' | 'en' | 'other'
  required_languages: string[]
  technologies: string[]
  tools: string[]
  methods: string[]
  skills: string[]
  soft_skills: string[]
  keywords: Keyword[]
  summary: string
}

export interface MissingSkill {
  term: string
  note: string
}

export interface TargetPlan {
  headline: string
  summary: string
  skill_groups: { label: string; items: { text: string; source: string }[] }[]
  missing: MissingSkill[]
  projects: { id: string; reason: string }[]
}

export interface Coverage {
  score: number
  present: string[]
  absent: string[]
}

export type ChangeGroup = 'En-tête' | 'Compétences' | 'Projets' | 'Expérience' | 'Langue'

export interface Chip {
  text: string
  // kept : déjà dans ce groupe ; added : connue, ajoutée ; pending : à confirmer ; removed : retirée.
  state: 'kept' | 'added' | 'pending' | 'removed'
}

export interface Line {
  text: string
  source: string
  // Tirée de la réserve de la bibliothèque.
  reserve: boolean
}

export interface Change {
  id: string
  group: ChangeGroup
  label: string
  kind: 'replace' | 'add' | 'remove'
  before: string
  // Pour une expérience, une puce par ligne.
  after: string
  warnings: string[]
  notes: string[]
  chips: Chip[]
  lines: Line[]
  // Termes absents du profil : accepter les confirme.
  pending: string[]
}

export interface Draft {
  id: string
  parent: string | null
  source: string
  options: { projects_count: number | null; language: 'auto' | 'fr' | 'en' }
  created_at: string
  language: 'fr' | 'en'
  source_language: 'fr' | 'en'
  offer_text: string
  offer_url: string | null
  analysis: OfferAnalysis
  plan: TargetPlan
  changes: Change[]
  projects: Record<string, { title: string; date?: string }>
  translation: Record<string, string>
  translation_source: Record<string, string>
  score_before: Coverage
  score_after: Coverage
  model: string
  seconds: number
  tokens: Record<string, number>
}

export type TargetEvent =
  | { type: 'step'; label: string }
  | { type: 'wait'; message: string }
  | { type: 'done'; draft: Draft }
  | { type: 'error'; message: string }

export interface TargetRequest {
  source: string
  text?: string
  url?: string
  projects_count?: number
  language: 'auto' | 'fr' | 'en'
}

export interface ApplyResult {
  slug: string
  compile: CompileResult
  score: Coverage | null
  // Termes confirmés ajoutés à la bibliothèque.
  library_added: string[]
}

export interface OfferInfo {
  text: string
  url: string | null
  analysis: OfferAnalysis
  missing: MissingSkill[]
  score: Coverage | null
}

// ─── Réglages de l'IA (app/settings.py) ──────────────────────────────────────

/** « relais » : Gemini par le relais de Yahya, avec un code d'accès (dossier relais/). */
export type Provider = 'relais' | 'gemini' | 'mistral' | 'ollama' | 'demo'

export interface AISettings {
  provider: Provider
  gemini_model: string
  gemini_fallbacks: string[]
  mistral_model: string
  relais_url: string
  relais_model: string
  ollama_model: string
  ollama_url: string
  temperature: number
}

export interface SettingsInfo {
  ai: AISettings
  keys: Record<Provider, boolean>
  usage: { month: string; calls: number; input: number; output: number; cost: number | null; last: string | null }
  blocked: Record<string, string>
  /** Le relais de Yahya a une adresse : « Gemini de Yahya » est utilisable. */
  relay_ready: boolean
  /** En ligne seulement : ce qu'il reste aujourd'hui à la personne connectée. */
  online?: OnlineAI | null
}

export interface OnlineAI {
  ok: boolean
  left: number | null
  quota: number | null
  exhausted: boolean
  message: string
}

/** Qui utilise l'appli : en ligne, la personne connectée ; en local, personne en particulier. */
export interface Me {
  mode: 'local' | 'serveur'
  email: string | null
  /** En ligne : cette personne administre le service (CVB_ADMIN). */
  admin: boolean
}

/** Administration : une personne invitée (ou l'administrateur). */
export interface AdminPerson {
  email: string
  invited: string | null
  removed: string | null
  last_seen: string | null
  admin: boolean
  cvs: number | null
  applications: number | null
  due: number | null
  ai_left: number | null
  ai_quota: number | null
  /** Sur la liste de Cloudflare (peut recevoir un code) ; null : Cloudflare non relié ou illisible. */
  cloudflare: boolean | null
}

export interface AdminPeople {
  people: AdminPerson[]
  spent: number | null
  budget: number | null
  cloudflare: boolean
  warning: string | null
}

export interface AdminPersonDetail {
  email: string
  cvs: CVSummary[]
}

export interface ConnectionTest {
  ok: boolean
  model: string
  seconds: number
  message: string
}

/** Une clé d'API essayée puis, si le fournisseur l'accepte, écrite dans .env. */
export interface KeyResult {
  ok: boolean
  saved: boolean
  model: string
  seconds: number
  message: string
}

export type KeyProvider = 'relais' | 'gemini' | 'mistral'

export interface MachineCheck {
  id: 'latex' | 'packages' | 'poppler'
  label: string
  /** null : pas vérifiable tant qu'un autre élément manque. */
  ok: boolean | null
  detail: string
  fix: string | null
}

export interface Machine {
  system: 'linux' | 'wsl' | 'docker' | 'autre'
  ok: boolean
  checks: MachineCheck[]
}

export interface WelcomeState {
  show: boolean
  /** L'écran de démarrage (modèle d'IA, machine) n'a pas encore été passé. */
  setup: boolean
}

// ─── Style (miroir de app/models/style.py) ───────────────────────────────────

export interface TextStyle {
  size: number | null
  leading: number | null
  bold: boolean
  italic: boolean
  color: string | null
  uppercase: boolean
  letter_spacing: number
  font: string | null
}

export type BlockKey =
  | 'name'
  | 'headline'
  | 'summary'
  | 'contact_label'
  | 'contact_strong'
  | 'contact_value'
  | 'section_title'
  | 'entry_title'
  | 'skill_label'
  | 'language_name'
  | 'experience_title'
  | 'experience_tag'
  | 'experience_place'
  | 'project_title'
  | 'project_tag'
  | 'date'
  | 'date_in_place'
  | 'body'

export type PaletteKey = 'primary' | 'secondary' | 'text' | 'accent' | 'band' | 'muted' | 'title_band' | 'link'

export interface ListSpacing {
  itemsep_pt: number
  itemsep_stretch_pt: number
  topsep_pt: number
  topsep_stretch_pt: number
}

export interface CVStyle {
  schema_version: number
  fonts: { main: string; ligatures: boolean; figures: 'proportional' | 'tabular' }
  palette: Record<PaletteKey, string>
  page: { margin_cm: number; base_size: 10 | 11 | 12; parskip_pt: number; line_spread: number }
  blocks: Record<BlockKey, TextStyle>
  photo: {
    visible: boolean
    shape: 'square' | 'rounded' | 'circle'
    position: 'right' | 'left'
    size_mode: 'match_text' | 'fixed'
    size_cm: number
    offset_x_pt: number
    offset_y_pt: number
    border_pt: number
    border_color: string
    corner_radius_pt: number
  }
  header: {
    align: 'left' | 'center'
    text_width: number
    name_gap_pt: number
    headline_gap_pt: number
    rule_visible: boolean
    rule_before_pt: number
    rule_after_pt: number
    rule_thickness_pt: number
    rule_color: string
    contact_separator: string
    after_contact_pt: number
  }
  columns: { layout: 'two' | 'one'; left_width: number; right_width: number; fill_page: boolean; bottom_safety_pt: number }
  band: { visible: boolean; color: string; column: Column; top_offset_pt: number }
  section_titles: {
    variant: 'rule' | 'band' | 'plain'
    band_color: string
    band_text_color: string
    band_radius_pt: number
    band_padding_pt: number
  }
  summary_frame: {
    visible: boolean
    border_pt: number
    border_color: string
    background_color: string | null
    radius_pt: number
    padding_pt: number
  }
  spacing: {
    section_gap_pt: number
    section_stretch: number
    entry_gap_pt: number
    entry_stretch: number
    skill_gap_pt: number
    skill_stretch: number
    title_rule_gap_pt: number
    title_rule_visible: boolean
    title_rule_thickness_pt: number
    title_rule_color: string
    after_title_pt: number
    place_gap_pt: number
  }
  lists: {
    leftmargin_pt: number
    labelsep_pt: number
    bullet: 'bullet' | 'dash' | 'square' | 'chevron'
    bullet_color: string | null
    left: ListSpacing
    right: ListSpacing
  }
  grid: { arraystretch: number; first_col: number; gap: number; second_col: number }
  links: { hide_boxes: boolean; color: string | null }
}

export interface FontInfo {
  id: string
  name: string
  category: 'sans' | 'serif'
}

export interface Theme {
  slug: string
  name: string
  style: CVStyle
}

// ─── Bibliothèque (miroir de app/models/library.py) ──────────────────────────

export type LibraryStatus = 'validé' | 'proposé'
export type LibrarySource = 'cv' | 'github' | 'manuel' | 'offre'
export type SkillLevel = 'notions' | 'pratique' | 'maîtrise'

export interface LibraryProject {
  id: string
  title: string
  date: string
  context: 'école' | 'stage' | 'perso' | 'autre' | null
  team: 'seul' | 'binôme' | 'équipe' | null
  techs: string[]
  description: string
  bullets: string[]
  link: string | null
  private: boolean
  notes: string
  source: LibrarySource
  status: LibraryStatus
}

export interface LibrarySkill {
  id: string
  name: string
  category: string
  aliases: string[]
  level: SkillLevel | null
  // Où elle a servi : « stage chez Logistica », « projet TrafficLens »…
  evidence: string
  source: LibrarySource
  status: LibraryStatus
}

export interface LibraryExperience {
  id: string
  title: string
  place: string
  dates: string
  // La réserve : toutes les puces vraies, pas seulement celles du CV.
  bullets: string[]
  source: LibrarySource
  status: LibraryStatus
}

export interface Library {
  projects: LibraryProject[]
  skills: LibrarySkill[]
  experiences: LibraryExperience[]
}

export interface FillResult {
  library: Library
  added: { projects: number; skills: number; experiences: number }
  github_error: string | null
}

export interface BulkResult {
  library: Library
  added: string[]
  known: string[]
}

export interface ProjectDraft {
  description: string
  bullets: string[]
  techs: string[]
}

// ─── Lettre de motivation (app/models/letter.py, app/api/letters.py) ─────────

export interface LetterContent {
  schema_version: number
  recipient: string[]
  place_date: string
  subject: string
  salutation: string
  paragraphs: string[]
  closing: string
  signature: string
  /** L'image de signature de la personne en bas de cette lettre (vrai par défaut). */
  signature_image?: boolean
  why: string
  detail: string
  mode: CVMode
}

export type SignatureSize = 'small' | 'medium' | 'large'

/** L'image de signature de la personne, la même pour toutes ses lettres. */
export interface SignatureInfo {
  present: boolean
  size: SignatureSize
  version: number | null
}

export interface LetterCheck {
  kind: 'tournure' | 'profil' | 'longueur'
  text: string
}

export interface LetterState {
  available: boolean
  letter: LetterContent | null
  checks: LetterCheck[]
  words: number
  pdf_version: number | null
  file_stem: string
}

export type RuleKind = 'lettre' | 'tournures'

// ─── Premier lancement et import d'un CV en PDF (app/api/welcome.py) ─────────

export interface ImportReading {
  id: string
  words: number
  pages: number | null
  photo: boolean
}

export interface ImportCheck {
  kind: 'absent' | 'unplaced'
  where: string
  text: string
}

export interface ImportResult {
  id: string
  content: CVContent
  photo: boolean
  checks: ImportCheck[]
  counts: { skills: number; experiences: number; projects: number }
}

export interface ApplyBaseResult {
  added: { skills: number; experiences: number; projects: number }
  compile: CompileResult
  /** Le CV classique écrit (« base » pour la première version). */
  slug: string
}

/** Un rectangle de la page, en points, depuis le coin haut gauche. */
export interface PageBox {
  x: number
  y: number
  w: number
  h: number
}

/** Ce qu'un clic sur l'aperçu a touché : l'en-tête, une ligne de coordonnées, une rubrique ou l'un de ses éléments. */
export interface PageLocation {
  area: 'header' | 'contact' | 'section'
  section: string | null
  item: number | null
  bullet: number | null
  line: number | null
  box: PageBox | null
}

/** Un élément du style repéré dans un PDF importé, et ce que l'appli en fait. */
export interface StyleFinding {
  key: string
  label: string
  found: string
  done: string
  badge: 'identique' | 'proche' | 'approché'
}

/** Un projet personnel, fait en quelques jours, qui rend vrais des mots-clés de l'offre. */
export interface ProjectIdea {
  name: string
  effort: string
  pitch: string
  why: string
  keywords: string[]
  stack: string[]
  modules: string[]
  data: string
  steps: string[]
  cv_line: string
  questions: string[]
}

export interface SavedIdeas {
  ideas: ProjectIdea[]
  created_at: string | null
}
