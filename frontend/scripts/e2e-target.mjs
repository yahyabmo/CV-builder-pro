// Parcours du ciblage d'une offre, avec un faux modèle à réponses enregistrées
// (aucun appel à Gemini) : Réglages, offre collée, relecture (compétence à
// confirmer, score en direct, « Je l'ai », relance, reprise après rechargement,
// refus, retouche, puce de réserve), création du CV, onglet Offre, lettre de
// motivation, règles dans Réglages.
//
// Il tourne sur les données d'essai de make e2e ; les réglages, la bibliothèque
// et les règles de cet essai sont tout de même remis tels quels à la fin.
//
//   node scripts/e2e-target.mjs <dossier des captures>

import { cpSync, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { launch, sleep } from './cdp.mjs'
import { API, APP, DATA, LOCAL } from './e2e-env.mjs'

const out = process.argv[2] ?? '.'
const SETTINGS = `${LOCAL}/settings.json`
const FAKE = `${LOCAL}/fake-llm.json`
const LIBRARY = `${DATA}/library`
const DRAFTS = `${DATA}/drafts`
const SLUG = 'essai-ciblage'
const started = Date.now()
const savedSettings = existsSync(SETTINGS) ? readFileSync(SETTINGS, 'utf8') : null
const backup = mkdtempSync(join(tmpdir(), 'bibliotheque-'))
const hadLibrary = existsSync(LIBRARY)
if (hadLibrary) cpSync(LIBRARY, join(backup, 'library'), { recursive: true })

// Les règles modifiées dans Réglages vont dans data/rules ; sans elles, celles de prompts/.
const RULES = ['lettre-regles', 'lettre-tournures'].map((name) => `${DATA}/rules/${name}.md`)
const savedRules = RULES.map((file) => (existsSync(file) ? readFileSync(file, 'utf8') : null))

const RESERVE = "Agent IA avec appel d'outils : requêtes SQL générées puis vérifiées sur PostgreSQL."
const OFFER = `Stage de fin d'études : ingénieur IA backend chez Acme, à Lyon.
Missions : concevoir des services Python (FastAPI), un pipeline RAG, déployer avec Docker et Kubernetes.
Profil : autonomie, esprit d'équipe, revue de code. Anglais professionnel.`

const item = (text, source = text) => ({ text, source })
const ANSWERS = {
  OfferAnalysis: {
    is_job_offer: true,
    job_title: 'Stage Ingénieur IA Backend',
    company: 'Acme',
    location: 'Lyon',
    contract: 'Stage',
    offer_language: 'fr',
    required_languages: ['anglais'],
    technologies: ['Python', 'FastAPI', 'RAG', 'Docker', 'Kubernetes'],
    tools: [],
    methods: ['revue de code'],
    skills: [],
    soft_skills: ['autonomie'],
    keywords: [
      { term: 'Python', importance: 3, category: 'techno' },
      { term: 'FastAPI', importance: 3, category: 'techno' },
      { term: 'RAG', importance: 2, category: 'techno' },
      { term: 'Docker', importance: 2, category: 'outil' },
      { term: 'Kubernetes', importance: 2, category: 'outil' },
      { term: 'revue de code', importance: 1, category: 'méthode' },
      { term: 'autonomie', importance: 1, category: 'soft skill' },
    ],
    summary: 'Concevoir et déployer des services d’IA en Python.',
  },
  TargetPlan: {
    headline: "Élève en école d'ingénieurs | IA & Backend Python",
    summary:
      "En dernière année d'école d'ingénieurs, à la recherche d'un stage de fin d'études en IA backend (Python, RAG, Kubernetes) à partir de février 2027.",
    skill_groups: [
      { label: 'Programmation', items: [item('Python'), item('SQL'), item('Kubernetes', '')] },
      { label: 'Outils', items: [item('Docker'), item('Git'), item('Linux')] },
    ],
    missing: [{ term: 'finance de marché', note: 'rien d’approchant' }],
    projects: [
      { id: 'cv-0', reason: 'Python.' },
      { id: 'cv-1', reason: 'Systèmes distribués.' },
    ],
  },
  LetterDraft: {
    recipient: ['Acme', 'Équipe IA', 'Lyon'],
    subject: 'Candidature au stage Ingénieur IA Backend',
    salutation: 'Madame, Monsieur,',
    paragraphs: [
      "C'est avec un grand intérêt que j'ai lu votre offre de stage en IA backend.",
      "Pendant mon stage, j'ai mis en production un modèle de prévision utilisé chaque semaine par l'équipe achats.",
      "Je serais heureux d'en parler avec vous lors d'un entretien.",
    ],
    closing: "Je vous prie d'agréer, Madame, Monsieur, mes salutations distinguées.",
  },
  ProjectDraft: { description: 'Agent IA de démonstration, avec outils et sources citées.', bullets: ['Outils.'], techs: ['Python'] },
  Rewrite: {
    experiences: [
      {
        exp: 'E1',
        bullets: [
          { ref: 'E1.5', text: RESERVE },
          { ref: 'E1.1', text: 'Prévision de la demande à 14 jours avec des modèles **LightGBM**, validation glissante.' },
          { ref: 'E1.2', text: 'Pipeline de données Python et SQL (PostgreSQL), relancé chaque nuit sous Docker.' },
          { ref: 'E1.3', text: 'API FastAPI qui sert les prévisions au logiciel de réapprovisionnement, avec tests.' },
        ],
      },
    ],
    texts: [],
  },
}

const WHY = "J'ai déjà mis un assistant IA en production seul ; ici, c'est le même sujet en équipe."
const FIXED = "Votre offre m'a arrêté : un backend d'IA qui doit tenir en production."

const browser = await launch({ height: 950 })
const check = (ok, text) => console.log(`${ok ? 'ok  ' : 'ÉCHEC'} ${text}`)
const byText = (selector, text) =>
  `[...document.querySelectorAll('${selector}')].find(e => e.textContent.trim().startsWith(${JSON.stringify(text)}))`
const click = (js) =>
  browser.evaluate(`(() => { const el = ${js}; if (!el) throw new Error('introuvable : ' + ${JSON.stringify(js)}); el.click(); return true })()`)
const type = (js, text) =>
  browser.evaluate(`(() => { const el = ${js}; const set = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value').set; set.call(el, ${JSON.stringify(text)}); el.dispatchEvent(new Event('input', {bubbles: true})); return true })()`)
const bodyHas = (text) => `document.body.innerText.includes(${JSON.stringify(text)})`
const card = (label) => `[...document.querySelectorAll('article')].find(a => a.querySelector('header')?.textContent.includes(${JSON.stringify(label)}))`
const chip = (text) => `[...document.querySelectorAll('article button[aria-pressed]')].find(b => b.textContent.trim() === ${JSON.stringify(text)})`
const score = `Number(document.querySelector('aside .text-3xl')?.textContent)`
const openTab = (label) =>
  browser.evaluate(`(() => { const t = ${byText('[role=tab]', label)}; t.dispatchEvent(new MouseEvent('mousedown', {bubbles: true})); t.click(); return true })()`)
const paragraph = (n) => `document.querySelector('textarea[aria-label="Paragraphe ${n}"]')`
const alerts = `(document.querySelector('[aria-label="Alertes de la lettre"]')?.textContent ?? '')`
const letterNow = async () => (await (await fetch(`${API}/api/cvs/${SLUG}/letter`)).json()).letter
// L'éditeur enregistre après une courte pause : on attend l'état enregistré.
const until = async (test, what) => {
  for (let i = 0; i < 50; i++) {
    if (await test()) return
    await sleep(300)
  }
  throw new Error(`jamais enregistré : ${what}`)
}

try {
  // ─── Réglages (les vrais, en lecture seule) ───
  await browser.goto(`${APP}/#/settings`)
  await browser.waitFor(bodyHas('Fournisseur du modèle'))
  const real = await (await fetch(`${API}/api/settings`)).json()
  check(!JSON.stringify(real).includes('AIza') && typeof real.keys.gemini === 'boolean', 'Réglages affichés, aucune clé renvoyée par l’API')
  await browser.screenshot(`${out}/reglages.png`)

  // ─── Mode démo : sans clé, l'offre d'exemple et ses réponses enregistrées ───
  mkdirSync(LOCAL, { recursive: true })
  writeFileSync(SETTINGS, JSON.stringify({ ...real.ai, provider: 'demo' }))
  await browser.goto(`${APP}/#/target`)
  await browser.waitFor(bodyHas('Mode démo.'), 10000)
  check(await browser.evaluate(`${byText('button', "Analyser l'offre")}.disabled`), 'démo : analyse bloquée tant que l’offre d’exemple n’est pas chargée')
  await browser.waitFor(`!${byText('button', "Charger l'offre d'exemple")}.disabled`, 10000)
  await click(byText('button', "Charger l'offre d'exemple"))
  await browser.waitFor(`document.querySelector('textarea[aria-label="Texte de l\\'offre"]').value.includes('Nordia')`, 5000)
  await click(byText('button', "Analyser l'offre"))
  await browser.waitFor(bodyHas('Tout accepter'), 30000)
  check(await browser.evaluate(`${chip('LangChain')}?.getAttribute('aria-pressed') === 'false'`), 'démo : ciblage de l’offre d’exemple, LangChain « à confirmer »')
  await browser.screenshot(`${out}/demo-relecture.png`)
  await click(byText('button', 'Abandonner'))
  await browser.waitFor(`document.querySelector('textarea[aria-label="Texte de l\\'offre"]')`, 5000)

  // ─── Faux modèle, bibliothèque d'essai (une puce de réserve) ───
  mkdirSync(LOCAL, { recursive: true })
  writeFileSync(FAKE, JSON.stringify(ANSWERS))
  writeFileSync(SETTINGS, JSON.stringify({ ...real.ai, provider: 'fake' }))
  rmSync(LIBRARY, { recursive: true, force: true })
  mkdirSync(LIBRARY)
  writeFileSync(`${LIBRARY}/experiences.json`, JSON.stringify([{ id: 'x', title: 'Stage Data Scientist', place: '', dates: '', bullets: [RESERVE], source: 'manuel', status: 'validé' }]))

  // Une autre page d'abord : la page de ciblage relit les réglages en s'ouvrant.
  await browser.goto(`${APP}/#/cvs`)
  await browser.waitFor(`document.querySelector('h1')?.textContent === 'Candidatures'`, 10000)
  await browser.goto(`${APP}/#/target`)
  await browser.waitFor(`document.querySelector('textarea[aria-label="Texte de l\\'offre"]')`)
  await type(`document.querySelector('textarea[aria-label="Texte de l\\'offre"]')`, OFFER)
  await click(byText('button', "Analyser l'offre"))
  await browser.waitFor(bodyHas('Tout accepter'), 30000)
  const cards = await browser.evaluate(`document.querySelectorAll('article').length`)
  check(cards >= 4, `proposition affichée : ${cards} changements`)
  check(await browser.evaluate(bodyHas('à confirmer')), 'éléments à confirmer signalés')

  // Une compétence absente du profil : proposée, pas cochée d'avance.
  check(await browser.evaluate(`${chip('Kubernetes')}?.getAttribute('aria-pressed') === 'false'`), 'Kubernetes proposé « à confirmer », hors du CV par défaut')
  check(await browser.evaluate(`${card('Accroche')}.querySelector('[role=checkbox]').getAttribute('aria-checked') === 'false'`), 'phrase avec un terme absent du profil : décochée')
  check(await browser.evaluate(`!!${card('Stage Data Scientist')}?.innerText.includes('de ta réserve')`), 'puce tirée de la réserve de la bibliothèque')
  check(await browser.evaluate(`!${card('Stage Data Scientist')}?.innerText.includes('**')`), 'pas de gras ajouté par l’IA')

  // Score en direct : confirmer Kubernetes le fait monter.
  await browser.waitFor(`${score} > 0`, 10000)
  const before = await browser.evaluate(score)
  await click(chip('Kubernetes'))
  await browser.waitFor(`${score} > ${before}`, 10000)
  check(true, `score en direct : ${before} → ${await browser.evaluate(score)} en confirmant Kubernetes`)

  // « Je l'ai » puis relance : sans réanalyser l'offre, choix repris.
  await click(`[...document.querySelectorAll('aside li')].find(li => li.textContent.includes('finance de marché')).querySelector('button')`)
  await browser.waitFor(`[...document.querySelectorAll('aside li')].find(li => li.textContent.includes('finance de marché'))?.textContent.includes('ajouté')`, 10000)
  await browser.screenshot(`${out}/cibler-relecture.png`)
  await click(byText('button', 'Relancer avec ma bibliothèque'))
  await browser.waitFor(`document.body.textContent.includes('(relancée)')`, 30000)
  check(await browser.evaluate(`${chip('Kubernetes')}?.getAttribute('aria-pressed') === 'true'`), 'relance : confirmation de Kubernetes reprise')
  check(await browser.evaluate(`!document.body.innerText.includes('finance de marché')`), 'relance : « Je l’ai » pris en compte (plus manquant)')

  // La relecture survit à un rechargement.
  await browser.goto(`${APP}/#/target`)
  await browser.waitFor(`document.body.textContent.includes('(relancée)')`, 15000)
  check(true, 'relecture reprise après rechargement')

  // Retoucher le titre, nommer, créer.
  await click(`${card('Titre')}.querySelector('button[aria-expanded]')`)
  await browser.waitFor(`${card('Titre')}.querySelector('textarea')`)
  await type(`${card('Titre')}.querySelector('textarea')`, 'Data Science | IA & Backend (essai)')
  await type(`document.querySelector('input[aria-label="Nom du nouveau CV"]')`, 'Essai ciblage')
  await sleep(400)
  await click(byText('button', 'Créer le CV'))
  await browser.waitFor(bodyHas('CV créé'), 60000)
  await browser.waitFor(bodyHas('Ajouté à ta bibliothèque'), 5000)
  await sleep(500)
  await browser.screenshot(`${out}/cibler-cree.png`)

  const cv = await (await fetch(`${API}/api/cvs/${SLUG}`)).json()
  const base = await (await fetch(`${API}/api/cvs/base`)).json()
  check(cv.content.header.headline === 'Data Science | IA & Backend (essai)', 'retouche du titre appliquée')
  check(cv.content.header.summary === base.content.header.summary, 'accroche non confirmée : inchangée')
  const skills = cv.content.sections.find((s) => s.kind === 'skills').items.map((g) => g.text).join(' ')
  check(skills.includes('Kubernetes'), 'compétence confirmée dans le CV')
  const stage = cv.content.sections.find((s) => s.kind === 'experience').items[0].bullets
  check(stage[0] === RESERVE && stage.length === 4, 'puce de réserve dans le CV, toujours 4 puces')
  const library = await (await fetch(`${API}/api/library`)).json()
  const confirmed = library.skills.filter((s) => s.source === 'offre').map((s) => s.name)
  check(confirmed.includes('Kubernetes') && confirmed.includes('finance de marché'), `bibliothèque complétée (${confirmed.join(', ')})`)

  await click(byText('button', 'Ouvrir le CV'))
  await browser.waitFor(`location.hash === '#/cv/${SLUG}'`)
  await browser.waitFor(`${byText('[role=tab]', 'Offre')}`)
  await browser.evaluate(`(() => { const t = ${byText('[role=tab]', 'Offre')}; t.dispatchEvent(new MouseEvent('mousedown', {bubbles: true})); t.click(); return true })()`)
  await browser.waitFor(bodyHas('Mots-clés de l\'offre dans le PDF'), 15000)
  await browser.screenshot(`${out}/onglet-offre.png`)
  check(true, 'onglet Offre du CV : score et mots-clés')

  // ─── Lettre de motivation ───
  await browser.goto(`${APP}/#/cv/${SLUG}`)
  await browser.waitFor(byText('[role=tab]', 'Lettre'))
  await openTab('Lettre')
  await browser.waitFor(byText('button', 'Générer ma lettre'), 15000)
  check(await browser.evaluate(bodyHas("L'aperçu de la lettre s'affiche ici")), 'aperçu en attente tant que la lettre n’est pas écrite')
  await type(`document.querySelector('textarea[aria-label="Pourquoi cette offre te parle"]')`, WHY)
  await click(byText('button', 'Générer ma lettre'))
  await browser.waitFor(paragraph(1), 60000)
  const generated = await letterNow()
  check(generated.why === WHY && generated.signature === 'Camille Laurent' && generated.place_date.startsWith('Lyon, le '), 'lettre écrite avec ta réponse, datée, signée')
  check(await browser.evaluate(`${alerts}.includes('grand intérêt')`), 'tournure « IA » signalée')
  await browser.waitFor(`document.querySelector('a[aria-label="Télécharger la lettre en PDF"]')?.getAttribute('href').includes('?v=')`, 30000)
  await browser.waitFor(`document.querySelector('canvas')`, 20000)
  const download = await browser.evaluate(`document.querySelector('a[aria-label="Télécharger la lettre en PDF"]').getAttribute('download')`)
  const pdf = await fetch(`${API}/api/cvs/${SLUG}/letter/pdf`)
  check(download.startsWith('camille_laurent_lettre_') && pdf.headers.get('content-type') === 'application/pdf', `PDF de la lettre dans l'aperçu, téléchargé sous ${download}`)
  await sleep(800)
  await browser.screenshot(`${out}/lettre.png`)

  // Retouche : la tournure corrigée sort des alertes ; Ctrl+Z et Ctrl+Y visent la lettre.
  await type(paragraph(1), FIXED)
  await browser.waitFor(`!${alerts}.includes('grand intérêt')`, 15000)
  await until(async () => (await letterNow()).paragraphs[0] === FIXED, 'paragraphe retouché')
  check(true, 'retouche enregistrée, alerte levée')
  await browser.key('z', { ctrl: true })
  await browser.waitFor(`${paragraph(1)}.value.includes('grand intérêt')`, 5000)
  await browser.key('y', { ctrl: true })
  await browser.waitFor(`${paragraph(1)}.value === ${JSON.stringify(FIXED)}`, 5000)
  check(true, 'Ctrl+Z puis Ctrl+Y sur la lettre')

  await click(`document.querySelector('button[aria-label="Monter le paragraphe 2"]')`)
  await until(async () => (await letterNow()).paragraphs[0] === ANSWERS.LetterDraft.paragraphs[1], 'paragraphes réordonnés')
  check(true, 'paragraphe remonté')

  await browser.evaluate(`(() => { navigator.clipboard.writeText = async (text) => { window.__copied = text }; return true })()`)
  await click(byText('button', 'Copier le texte'))
  await browser.waitFor(`typeof window.__copied === 'string'`, 5000)
  const copied = await browser.evaluate('window.__copied')
  check(copied.startsWith('Madame, Monsieur,') && copied.includes(FIXED) && !copied.includes('Objet'), 'texte copié : le corps seul')

  await click(byText('[role=radio]', 'LaTeX'))
  await browser.waitFor(`document.querySelector('.monaco-editor .view-lines')?.textContent.includes('documentclass')`, 20000)
  check(true, 'code LaTeX de la lettre dans l’éditeur')
  await click(byText('[role=radio]', 'Texte'))
  await browser.waitFor(paragraph(1))

  await browser.goto(`${APP}/#/cv/base`)
  await browser.waitFor(byText('[role=tab]', 'Lettre'))
  await openTab('Lettre')
  await browser.waitFor(bodyHas('Ce CV ne vise aucune offre'), 10000)
  check(true, 'CV non ciblé : « cible une offre d’abord »')

  // ─── Règles dans Réglages : un champ par règle ───
  const section = (title) => `document.querySelector('section[aria-label="${title}"]')`
  const TURNS = 'Lettre de motivation : tournures à bannir'
  const turnFields = `${section(TURNS)}.querySelectorAll('textarea')`
  await browser.goto(`${APP}/#/settings`)
  await browser.waitFor(`${section('Lettre de motivation : tes règles')}?.querySelectorAll('textarea').length >= 5`, 10000)
  check(true, 'règles de la lettre, une par champ')
  const count = await browser.evaluate(`${turnFields}.length`)
  await click(`[...${section(TURNS)}.querySelectorAll('button')].find(b => b.textContent.includes('Ajouter une tournure'))`)
  await browser.waitFor(`${turnFields}.length === ${count + 1} && document.activeElement === ${turnFields}[${count}]`)
  await type(`${turnFields}[${count}]`, 'tournure ajoutée par l’essai')
  await click(`[...${section(TURNS)}.querySelectorAll('button')].find(b => b.textContent.includes('Enregistrer'))`)
  await until(async () => (await (await fetch(`${API}/api/rules/tournures`)).json()).rules.includes('tournure ajoutée par l’essai'), 'tournure ajoutée')
  await browser.waitFor(`!${section(TURNS)}.textContent.includes('Modifications non enregistrées')`)
  await click(`${section(TURNS)}.querySelector('button[aria-label="Supprimer la règle ${count + 1}"]')`)
  await click(`[...${section(TURNS)}.querySelectorAll('button')].find(b => b.textContent.includes('Enregistrer'))`)
  await until(async () => (await (await fetch(`${API}/api/rules/tournures`)).json()).rules.length === count, 'tournure supprimée')
  check(true, 'tournure ajoutée, enregistrée, puis supprimée')
  await browser.screenshot(`${out}/reglages-regles.png`)

  const errors = browser.logs.filter((l) => /EXCEPTION|console.error/.test(l))
  check(errors.length === 0, `aucune erreur JavaScript${errors.length ? ' : ' + errors.join(' | ') : ''}`)
} catch (error) {
  check(false, error.message)
  await browser.screenshot(`${out}/echec-ciblage.png`).catch(() => undefined)
  console.log(browser.logs.join('\n'))
  process.exitCode = 1
} finally {
  browser.close()
  rmSync(FAKE, { force: true })
  RULES.forEach((file, i) => (savedRules[i] == null ? rmSync(file, { force: true }) : writeFileSync(file, savedRules[i])))
  if (savedSettings != null) writeFileSync(SETTINGS, savedSettings)
  else rmSync(SETTINGS, { force: true })
  rmSync(LIBRARY, { recursive: true, force: true })
  if (hadLibrary) cpSync(join(backup, 'library'), LIBRARY, { recursive: true })
  rmSync(backup, { recursive: true, force: true })
  await fetch(`${API}/api/cvs/${SLUG}`, { method: 'DELETE' }).catch(() => undefined)
  rmSync(`${DATA}/cvs/${SLUG}`, { recursive: true, force: true })
  if (existsSync(`${DATA}/corbeille`))
    for (const entry of readdirSync(`${DATA}/corbeille`))
      if (entry.startsWith(`${SLUG}-`)) rmSync(`${DATA}/corbeille/${entry}`, { recursive: true, force: true })
  if (existsSync(DRAFTS))
    for (const entry of readdirSync(DRAFTS))
      if (statSync(join(DRAFTS, entry)).mtimeMs >= started) rmSync(join(DRAFTS, entry), { force: true })
  writeFileSync(join(out, 'e2e-target.done'), new Date().toISOString())
}
