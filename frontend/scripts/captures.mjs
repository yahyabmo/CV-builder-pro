// Les captures du README, en mode clair, prises sur le CV fictif (Camille Laurent)
// et des offres inventées, en mode démo (réponses enregistrées, aucune clé) :
// démarrage (modèle d'IA, machine), import PDF (son style repéré), Candidatures, relecture d'un ciblage, éditeur
// (clic sur l'aperçu), idées de projet, lettre, couleurs et palettes, bibliothèque.
//
// Lancé par make captures, sur un serveur d'essai à part : tes données ne sont
// jamais lues.
//
//   node scripts/captures.mjs <dossier des captures>

import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { join } from 'node:path'
import { launch, sleep } from './cdp.mjs'
import { API, APP, DATA, LOCAL } from './e2e-env.mjs'

const out = process.argv[2] ?? '.'
mkdirSync(out, { recursive: true })
const DEMO = '../demo'
const answers = JSON.parse(readFileSync(join(DEMO, 'reponses-ia.json'), 'utf8'))
const offerText = readFileSync(join(DEMO, 'offre-exemple.txt'), 'utf8')

const byText = (selector, text) => `[...document.querySelectorAll('${selector}')].find(e => e.textContent.trim().startsWith(${JSON.stringify(text)}))`
const bodyHas = (text) => `document.body.innerText.includes(${JSON.stringify(text)})`
const call = async (path, init = {}) => {
  const answer = await fetch(`${API}${path}`, { headers: { 'Content-Type': 'application/json' }, ...init })
  if (!answer.ok) throw new Error(`${path} : ${answer.status} ${await answer.text()}`)
  return answer.json()
}
const day = (offset) => new Date(Date.now() + offset * 86_400_000).toISOString().slice(0, 10)

// Des offres inventées ; les mots-clés de l'offre d'exemple, plus ou moins nombreux.
// Indices des mots-clés gardés : des offres plus ou moins proches du CV.
const OFFERS = [
  { name: 'Nordia, data scientist IA', company: 'Nordia', title: 'Stage Data Scientist IA générative', city: 'Lyon', contract: 'Stage', keys: null, status: 'sent', sent: -11 },
  { name: 'Aubépine Énergie, data analyst', company: 'Aubépine Énergie', title: 'Data analyst, prévision de consommation', city: 'Grenoble', contract: 'Stage', keys: [2, 7, 5, 10, 12, 13, 15, 14], status: 'interview', sent: -16 },
  { name: 'Kestrel Robotics, vision', company: 'Kestrel Robotics', title: 'Ingénieur vision par ordinateur', city: 'Toulouse', contract: 'Stage', keys: [8, 2, 9, 10, 12, 14], status: 'todo' },
  { name: 'Lumio Santé, data scientist', company: 'Lumio Santé', title: 'Data scientist, parcours patients', city: 'Paris', contract: 'CDI', keys: [0, 1, 2, 3, 4, 7, 13, 15, 9], status: 'offer', sent: -30 },
  { name: 'Maison Verlaine, analyste', company: 'Maison Verlaine', title: 'Analyste données marketing', city: 'Nantes', contract: 'Stage', keys: [7, 2, 10, 12, 14, 15], status: 'refused', sent: -25 },
]

async function prepare() {
  const settings = await call('/api/settings')
  writeFileSync(`${LOCAL}/settings.json`, JSON.stringify({ ...settings.ai, provider: 'demo' }))
  // Le CV de base compilé : sa miniature dans le menu.
  await call('/api/cvs/base/compile', { method: 'POST' })
  const slugs = []
  for (const offer of OFFERS) {
    const { slug } = await call('/api/cvs', { method: 'POST', body: JSON.stringify({ name: offer.name, source: 'base' }) })
    const folder = `${DATA}/cvs/${slug}`
    const analysis = {
      ...answers.OfferAnalysis,
      company: offer.company,
      job_title: offer.title,
      location: offer.city,
      contract: offer.contract,
      keywords: offer.keys ? offer.keys.map((i) => answers.OfferAnalysis.keywords[i]) : answers.OfferAnalysis.keywords,
    }
    writeFileSync(`${folder}/analysis.json`, JSON.stringify({ draft: 'capture', analysis, plan: answers.TargetPlan }))
    writeFileSync(`${folder}/offer.txt`, offerText)
    const meta = JSON.parse(readFileSync(`${folder}/meta.json`, 'utf8'))
    writeFileSync(`${folder}/meta.json`, JSON.stringify({ ...meta, company: offer.company, position: offer.title }))
    if (offer.status !== 'todo') {
      await call(`/api/cvs/${slug}/application`, { method: 'PATCH', body: JSON.stringify({ status: 'sent', sent_on: day(offer.sent) }) })
      if (offer.status !== 'sent') await call(`/api/cvs/${slug}/application`, { method: 'PATCH', body: JSON.stringify({ status: offer.status }) })
    }
    // Le score de la carte est mesuré sur le PDF, à la lecture de l'offre.
    await call('/api/target/offer/' + slug)
    slugs.push(slug)
  }
  return slugs
}

const browser = await launch({ height: 900 })
const click = (js) => browser.evaluate(`(() => { const el = ${js}; if (!el) throw new Error('introuvable : ' + ${JSON.stringify(js)}); el.click(); return true })()`)
const type = (js, text) =>
  browser.evaluate(`(() => { const el = ${js}; const set = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value').set; set.call(el, ${JSON.stringify(text)}); el.dispatchEvent(new Event('input', {bubbles: true})); return true })()`)
const openTab = (label) =>
  browser.evaluate(`(() => { const t = ${byText('[role=tab]', label)}; t.dispatchEvent(new MouseEvent('mousedown', {bubbles: true})); t.click(); return true })()`)
const shot = async (name) => {
  await sleep(400)
  await browser.screenshot(join(out, name))
  console.log(`capture ${name}`)
}
const drawn = `[...document.querySelectorAll('[data-front=true] canvas')].some(c => c.width > 300)`

try {
  // ─── Le démarrage : « Gemini de Yahya » choisi, le code pas encore collé, la machine vérifiée ───
  await browser.goto(`${APP}/#/cvs`)
  await browser.waitFor(bodyHas("Réglons l'essentiel avant de commencer."), 15000)
  await click(byText('button', 'Recommandé'))
  await browser.waitFor(`document.querySelectorAll('ul[aria-label="Vérifications de la machine"] li').length === 4 && ${bodyHas('Ton code d’accès')}`, 15000)
  await shot('demarrage.png')
  await click(byText('button', 'Plus tard : découvrir en mode Démo'))

  // ─── Import d'un CV PDF : la relecture ───
  await browser.waitFor(bodyHas('Commençons par ton CV de base.'), 15000)
  const settings = await call('/api/settings')
  writeFileSync(`${LOCAL}/settings.json`, JSON.stringify({ ...settings.ai, provider: 'demo' }))
  await click(byText('button', 'Recommandé'))
  await browser.waitFor(bodyHas('Mode démo'), 10000)
  await click(byText('button', "Essayer avec le PDF d'exemple"))
  await browser.waitFor(`document.querySelector('section[aria-label="Ton PDF d\\'origine"] canvas')?.width > 100`, 30000)
  await click(byText('[role=radio]', 'Style'))
  await browser.waitFor(bodyHas('Repéré dans ton PDF'), 15000)
  await browser.waitFor(`document.querySelectorAll('canvas').length >= 2`, 30000)
  await shot('import.png')
  await call('/api/welcome/dismiss', { method: 'POST' })

  const [nordia] = await prepare()
  // La bibliothèque, remplie depuis le CV de base seul : jamais le compte GitHub de la machine.
  await call('/api/library/fill?github=false', { method: 'POST' })

  // ─── Candidatures ───
  await browser.goto(`${APP}/#/cvs`)
  await browser.waitFor(`document.querySelectorAll('article').length >= ${OFFERS.length} && ${bodyHas('relance')}`, 15000)
  await browser.waitFor(`[...document.querySelectorAll('article img')].every(i => i.complete)`, 10000)
  await shot('candidatures.png')

  // ─── Ciblage d'une offre : la relecture des propositions ───
  await browser.goto(`${APP}/#/target`)
  await browser.waitFor(bodyHas('Mode démo.'), 10000)
  await browser.waitFor(`!${byText('button', "Charger l'offre d'exemple")}.disabled`, 10000)
  await click(byText('button', "Charger l'offre d'exemple"))
  await browser.waitFor(`document.querySelector('textarea[aria-label="Texte de l\\'offre"]').value.includes('Nordia')`, 5000)
  await click(byText('button', "Analyser l'offre"))
  await browser.waitFor(bodyHas('Tout accepter'), 30000)
  await shot('ciblage.png')
  await click(byText('button', 'Abandonner'))

  // ─── L'éditeur, menu replié : un clic sur l'aperçu mène au champ ───
  await browser.goto(`${APP}/#/cv/${nordia}`)
  await browser.waitFor(drawn, 30000)
  await click(`document.querySelector('button[aria-label="Replier le menu"]')`)
  await sleep(600)
  await browser.waitFor(`document.querySelector('[role=region][aria-label="Correspondance à l\\'offre"]')`, 15000)
  const xml = execFileSync('pdftotext', ['-bbox', `${DATA}/cvs/${nordia}/cv.pdf`, '-'], { encoding: 'utf8' })
  const word = [...xml.matchAll(/xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">Logistica</g)][0]
  const x = (Number(word[1]) + Number(word[3])) / 2
  const y = (Number(word[2]) + Number(word[4])) / 2
  await browser.evaluate(`(() => {
    const page = document.querySelector('[data-front=true]')
    const box = page.getBoundingClientRect()
    const scale = box.width / 595.28
    const cx = box.left + ${x} * scale, cy = box.top + ${y} * scale
    document.elementFromPoint(cx, cy).dispatchEvent(new MouseEvent('click', { bubbles: true, clientX: cx, clientY: cy }))
    return true
  })()`)
  await browser.waitFor(`document.activeElement?.closest('[data-item="experience/0"]')`, 8000)
  // Le temps que le formulaire finisse de défiler ; le cadre de l'aperçu reste 2,4 s.
  await sleep(700)
  await browser.screenshot(join(out, 'editeur.png'))
  console.log('capture editeur.png')

  // ─── Idées de projet : trois projets pour ce qui manque, et un cahier des charges ───
  await openTab('Offre')
  await browser.waitFor(byText('button', 'Proposer 3 idées'), 15000)
  await click(byText('button', 'Proposer 3 idées'))
  await browser.waitFor(`document.querySelectorAll('section[aria-label="Idées de projet"] article').length === 3`, 30000)
  await browser.evaluate(`document.querySelector('section[aria-label="Idées de projet"]').scrollIntoView({ block: 'start' }); true`)
  await click(byText('button', 'Voir le cahier des charges'))
  await browser.waitFor(`document.querySelector('[data-slot=sheet-content]')?.textContent.includes('Étapes')`, 5000)
  await shot('idees-projet.png')
  await browser.key('Escape')
  await browser.waitFor(`!document.querySelector('[data-slot=sheet-content]')`, 5000)

  // ─── Lettre de motivation ───
  await openTab('Lettre')
  await browser.waitFor(byText('button', 'Générer ma lettre'), 15000)
  await type(
    `document.querySelector('textarea[aria-label="Pourquoi cette offre te parle"]')`,
    "J'ai déjà construit un assistant de questions sur des documents ; ici, il servirait à des techniciens sur le terrain.",
  )
  await click(byText('button', 'Générer ma lettre'))
  await browser.waitFor(`document.querySelector('textarea[aria-label="Paragraphe 1"]')`, 60000)
  await browser.waitFor(`document.querySelector('a[aria-label="Télécharger la lettre en PDF"]')?.getAttribute('href').includes('?v=')`, 30000)
  await browser.waitFor(drawn, 30000)
  await shot('lettre.png')

  // ─── Couleurs et palettes ───
  await openTab('Style')
  await browser.waitFor(`document.querySelectorAll('button[aria-label^="Palette "]').length === 30`, 15000)
  await click(`document.querySelector('button[aria-label="Palette Émeraude"]')`)
  // Le PDF recompilé avec la nouvelle palette, affiché devant.
  await sleep(800)
  await browser.waitFor(`document.querySelector('[role=status]')?.textContent.startsWith('Enregistré')`, 30000)
  await browser.waitFor(`document.querySelector('[data-front=true]')?.dataset.pdf === document.querySelector('a[download]')?.getAttribute('href')`, 30000)
  await browser.waitFor(drawn, 30000)
  await shot('couleurs.png')

  // ─── Bibliothèque ───
  await browser.goto(`${APP}/#/library`)
  await browser.waitFor(`document.querySelector('h1')?.textContent === 'Bibliothèque' && ${bodyHas('Python')}`, 15000)
  await shot('bibliotheque.png')
} finally {
  browser.close()
}
