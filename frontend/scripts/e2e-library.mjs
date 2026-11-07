// Parcours des Candidatures et de la Bibliothèque :
// créer un CV, en suivre la candidature (statut, date d'envoi, relance en retard,
// « Relancée aujourd'hui », historique, vue en colonnes), le renommer, le
// supprimer ; remplir la
// bibliothèque (CV et GitHub), ajouter des compétences en lot, régler un
// niveau, écrire une puce de réserve, valider les projets proposés.
//
// Les données réelles ne sont pas touchées : la bibliothèque est sauvegardée
// puis remise telle quelle, le CV d'essai et sa corbeille sont effacés.
//
//   node scripts/e2e-library.mjs <dossier des captures>

import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync, cpSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { launch, sleep } from './cdp.mjs'
import { API, APP, DATA } from './e2e-env.mjs'

const out = process.argv[2] ?? '.'
const LIBRARY = `${DATA}/library`
const backup = mkdtempSync(join(tmpdir(), 'bibliotheque-'))
const hadLibrary = existsSync(LIBRARY)
if (hadLibrary) cpSync(LIBRARY, join(backup, 'library'), { recursive: true })

const browser = await launch({ height: 950 })
const check = (ok, text) => console.log(`${ok ? 'ok  ' : 'ÉCHEC'} ${text}`)
const byText = (selector, text) => `[...document.querySelectorAll('${selector}')].find(e => e.textContent.trim().startsWith(${JSON.stringify(text)}))`
const click = (js) => browser.evaluate(`(() => { const el = ${js}; if (!el) throw new Error('introuvable : ' + ${JSON.stringify(js)}); el.click(); return true })()`)
// Radix ouvre ses menus au « pointerdown ».
const press = (js) => browser.evaluate(`(() => { const el = ${js}; if (!el) throw new Error('introuvable : ' + ${JSON.stringify(js)}); el.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true, button: 0, pointerType: 'mouse'})); return true })()`)
const type = (js, text) => browser.evaluate(`(() => { const el = ${js}; const set = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value').set; set.call(el, ${JSON.stringify(text)}); el.dispatchEvent(new Event('input', {bubbles: true})); return true })()`)
const created = []
const bodyHas = (text) => `document.body.innerText.includes(${JSON.stringify(text)})`
// L'appli enregistre puis relit : on attend l'état voulu côté serveur.
const until = async (test, what) => {
  for (let i = 0; i < 50; i++) {
    if (await test()) return
    await sleep(200)
  }
  throw new Error(`jamais enregistré : ${what}`)
}

try {
  // ─── Candidatures ───
  await browser.goto(`${APP}/#/cvs`)
  await browser.waitFor(`document.querySelector('h1')?.textContent === 'Candidatures' && document.querySelectorAll('article').length > 0`)
  check(await browser.evaluate(bodyHas('Sans offre visée')), 'page « Candidatures » affichée, CV sans offre signalé')

  await click(byText('button', 'Nouveau CV'))
  await browser.waitFor(`document.querySelector('input[placeholder^="ex. Thales"]')`)
  await type(`document.querySelector('input[placeholder^="ex. Thales"]')`, 'Essai galerie')
  await click(`document.querySelector('input[placeholder^="ex. Thales"]').form.querySelector('button[type=submit]')`)
  await browser.waitFor(`location.hash === '#/cv/essai-galerie'`, 20000)
  created.push('essai-galerie')
  await browser.waitFor(`document.querySelector('[data-front=true] canvas')?.width > 400`, 30000)
  check(true, 'nouveau CV créé, ouvert, et son PDF affiché')

  // Comme après un ciblage : une offre visée, avec son analyse.
  const folder = `${DATA}/cvs/essai-galerie`
  const meta = JSON.parse(readFileSync(`${folder}/meta.json`, 'utf8'))
  writeFileSync(`${folder}/meta.json`, JSON.stringify({ ...meta, company: 'Laboratoire Exemple', position: 'Ingénieur IA (essai)', score: 72 }))
  writeFileSync(`${folder}/analysis.json`, JSON.stringify({ analysis: { location: 'Labo, 292 rue Saint-Martin, 75003 Paris', contract: 'Stage' }, plan: {} }))

  const card = `[...document.querySelectorAll('article')].find(a => a.textContent.includes('Ingénieur IA (essai)'))`
  await browser.goto(`${APP}/#/cvs`)
  await browser.waitFor(card, 10000)
  check(await browser.evaluate(`${card}.textContent.includes('Paris · Stage') && ${card}.textContent.includes('À envoyer')`), 'carte : ville tirée de l’adresse, statut « À envoyer »')

  // La fiche : statut, puis une date d'envoi vieille de douze jours.
  await click(`${card}.querySelector('button')`)
  await browser.waitFor(`document.querySelector('[data-slot=sheet-content] [role=radiogroup]')`, 5000)
  await click(byText('[data-slot=sheet-content] [role=radio]', 'Envoyée'))
  const application = async () => (await (await fetch(`${API}/api/cvs/essai-galerie`)).json()).meta.application
  await until(async () => (await application()).status === 'sent', 'statut envoyé')
  const day = new Date(Date.now() - 12 * 86_400_000)
  const sent = new Date(day.getTime() - day.getTimezoneOffset() * 60_000).toISOString().slice(0, 10)
  await type(`document.querySelector('input[aria-label="Date d\\'envoi"]')`, sent)
  await until(async () => (await application()).sent_on === sent, 'date d’envoi')
  check(true, 'fiche : statut « Envoyée » et date d’envoi enregistrés')
  await browser.screenshot(`${out}/candidature-fiche.png`)
  await browser.evaluate(`document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}))`)
  await browser.waitFor(`!document.querySelector('[data-slot=sheet-content]')`, 5000)

  const band = `document.querySelector('section[aria-label="À relancer"]')`
  await browser.waitFor(`${band}?.textContent.includes('Ingénieur IA (essai)') && ${band}.textContent.includes('jours de retard')`, 10000)
  const badge = await browser.evaluate(`document.querySelector('nav [aria-label$="à faire"]')?.textContent`)
  check(Number(badge) >= 1, `relance en retard : bandeau « À relancer » et badge (${badge})`)
  await browser.screenshot(`${out}/candidatures.png`)

  await click(`[...${band}.querySelectorAll('div')].find(d => d.textContent.includes('Ingénieur IA (essai)') && d.querySelector('button')).querySelectorAll('button')[1]`)
  await browser.waitFor(`!${band}?.textContent.includes('Ingénieur IA (essai)')`, 10000)
  check((await application()).history[0].text === 'Relance faite', '« Relancée aujourd’hui » : rappel levé, relance dans l’historique')

  // Vue en colonnes, gardée après rechargement.
  await click(byText('[role=radio]', 'Colonnes'))
  const column = `document.querySelector('section[aria-label="Envoyée"]')`
  await browser.waitFor(`${column}?.textContent.includes('Ingénieur IA (essai)')`, 5000)
  await browser.goto(`${APP}/#/library`)
  await browser.goto(`${APP}/#/cvs`)
  await browser.waitFor(`${column}?.textContent.includes('Ingénieur IA (essai)')`, 10000)
  check(true, 'vue en colonnes : carte dans « Envoyée », choix gardé')
  await browser.screenshot(`${out}/candidatures-colonnes.png`)
  await click(byText('[role=radio]', 'Cartes'))
  await browser.waitFor(card, 5000)

  // Renommer par le menu de la carte.
  await press(`document.querySelector('button[aria-label="Actions pour Essai galerie"]')`)
  await browser.waitFor(`${byText('[role=menuitem]', 'Renommer')}`)
  await click(byText('[role=menuitem]', 'Renommer'))
  await browser.waitFor(`document.querySelector('[role=dialog] input')?.value === 'Essai galerie'`)
  await type(`document.querySelector('[role=dialog] input')`, 'Essai galerie renommé')
  await click(`document.querySelector('[role=dialog] button[type=submit]')`)
  await browser.waitFor(`document.querySelector('button[aria-label="Actions pour Essai galerie renommé"]')`, 10000)
  const renamed = await (await fetch(`${API}/api/cvs/essai-galerie`)).json()
  check(renamed.meta.name === 'Essai galerie renommé', 'CV renommé (le dossier garde son identifiant)')

  // Supprimer (corbeille), une fois la fenêtre de renommage tout à fait fermée.
  await browser.waitFor(`!document.querySelector('[role=dialog]') && document.body.style.pointerEvents !== 'none'`, 5000)
  await press(`document.querySelector('button[aria-label="Actions pour Essai galerie renommé"]')`)
  await browser.waitFor(`${byText('[role=menuitem]', 'Supprimer')}`)
  await click(byText('[role=menuitem]', 'Supprimer'))
  await browser.waitFor(`${byText('[role=alertdialog] button', 'Supprimer')}`)
  await click(byText('[role=alertdialog] button', 'Supprimer'))
  await browser.waitFor(`!${card}`, 10000)
  check((await fetch(`${API}/api/cvs/essai-galerie`)).status === 404, 'CV supprimé (mis à la corbeille)')

  // ─── Bibliothèque ───
  await browser.goto(`${APP}/#/library`)
  await browser.waitFor(`document.querySelector('h1')?.textContent === 'Bibliothèque'`)
  await browser.waitFor(`${byText('button', 'Remplir depuis mon CV et GitHub')}?.disabled === false`)
  await click(byText('button', 'Remplir depuis mon CV et GitHub'))
  // GitHub (vrais dépôts, par gh) peut prendre quelques secondes.
  await browser.waitFor(`[...document.querySelectorAll('button')].some(b => b.textContent.trim() === 'Python') && !document.querySelector('header .animate-spin')`, 90000)
  await sleep(1500)
  const skills = JSON.parse(readFileSync(`${LIBRARY}/skills.json`, 'utf8'))
  const experiences = JSON.parse(readFileSync(`${LIBRARY}/experiences.json`, 'utf8'))
  const projects = JSON.parse(readFileSync(`${LIBRARY}/projects.json`, 'utf8'))
  check(skills.find((s) => s.name === 'Python')?.status === 'validé', `compétences du CV validées d'office (${skills.length})`)
  check(experiences.length === 3 && experiences[0].bullets.length === 4, 'expériences du CV et leurs puces reprises')
  check(projects.filter((p) => p.source === 'cv' && p.status === 'validé').length === 4, `projets du CV validés, ${projects.filter((p) => p.source === 'github').length} dépôt(s) GitHub proposé(s)`)

  // Ajout en lot, catégorie devinée.
  await type(`document.querySelector('textarea[aria-label="Compétences à ajouter"]')`, 'Kubernetes, Streamlit')
  await click(`document.querySelector('textarea[aria-label="Compétences à ajouter"]').form.querySelector('button[type=submit]')`)
  await browser.waitFor(`[...document.querySelectorAll('button')].some(b => b.textContent.trim() === 'Kubernetes')`, 10000)
  const added = JSON.parse(readFileSync(`${LIBRARY}/skills.json`, 'utf8'))
  check(added.find((s) => s.name === 'Kubernetes')?.category === 'Cloud & DevOps', 'ajout en lot, catégorie devinée (Kubernetes → Cloud & DevOps)')

  // Niveau et « où » d'une compétence.
  await click(`[...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Kubernetes')`)
  await browser.waitFor(`document.querySelector('[role=dialog] [role=radio]')`)
  await click(`[...document.querySelectorAll('[role=dialog] [role=radio]')].find(b => b.textContent === 'Notions')`)
  await sleep(1200)
  const leveled = JSON.parse(readFileSync(`${LIBRARY}/skills.json`, 'utf8'))
  check(leveled.find((s) => s.name === 'Kubernetes')?.level === 'notions', 'niveau enregistré')
  await browser.evaluate(`document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}))`)
  await sleep(500)
  await browser.screenshot(`${out}/bibliotheque-competences.png`)

  // Réserve de puces d'une expérience.
  await browser.evaluate(`(() => { const t = ${byText('[role=tab]', 'Expériences')}; t.dispatchEvent(new MouseEvent('mousedown', {bubbles: true})); t.click(); return true })()`)
  await browser.waitFor(`document.querySelector('textarea[aria-label^="Puce 1 de Stage"]')`)
  await click(`[...document.querySelector('textarea[aria-label^="Puce 1 de Stage"]').closest('article').querySelectorAll('button')].find(b => b.textContent.trim() === 'Puce')`)
  await browser.waitFor(`document.querySelector('textarea[aria-label="Puce 5 de Stage Data Scientist"]')`)
  await type(`document.querySelector('textarea[aria-label="Puce 5 de Stage Data Scientist"]')`, 'Une puce de réserve écrite dans le navigateur.')
  await sleep(1200)
  const reserve = JSON.parse(readFileSync(`${LIBRARY}/experiences.json`, 'utf8'))
  check(reserve[0].bullets[4] === 'Une puce de réserve écrite dans le navigateur.', 'puce de réserve enregistrée')
  await browser.screenshot(`${out}/bibliotheque-experiences.png`)

  // Projets : tout valider.
  await browser.evaluate(`(() => { const t = ${byText('[role=tab]', 'Projets')}; t.dispatchEvent(new MouseEvent('mousedown', {bubbles: true})); t.click(); return true })()`)
  await browser.waitFor(bodyHas('Mes projets'))
  if (await browser.evaluate(`!!${byText('button', 'Tout valider')}`)) {
    await click(byText('button', 'Tout valider'))
    await sleep(1200)
  }
  const all = JSON.parse(readFileSync(`${LIBRARY}/projects.json`, 'utf8'))
  check(all.every((p) => p.status === 'validé'), `projets tous validés (${all.length})`)
  await browser.screenshot(`${out}/bibliotheque-projets.png`)

  const errors = browser.logs.filter((l) => /EXCEPTION|console.error/.test(l))
  check(errors.length === 0, `aucune erreur JavaScript${errors.length ? ' : ' + errors.join(' | ') : ''}`)
} catch (error) {
  check(false, error.message)
  await browser.screenshot(`${out}/e2e-library-echec.png`).catch(() => undefined)
  console.log(browser.logs.join('\n'))
  process.exitCode = 1
} finally {
  browser.close()
  // Remise en état : bibliothèque d'origine, CV d'essai et corbeille effacés.
  rmSync(LIBRARY, { recursive: true, force: true })
  if (hadLibrary) cpSync(join(backup, 'library'), LIBRARY, { recursive: true })
  rmSync(backup, { recursive: true, force: true })
  for (const slug of created) {
    await fetch(`${API}/api/cvs/${slug}`, { method: 'DELETE' }).catch(() => undefined)
    rmSync(`${DATA}/cvs/${slug}`, { recursive: true, force: true })
  }
  if (existsSync(`${DATA}/corbeille`)) {
    for (const entry of (await import('node:fs')).readdirSync(`${DATA}/corbeille`)) {
      if (created.some((slug) => entry.startsWith(`${slug}-`))) rmSync(`${DATA}/corbeille/${entry}`, { recursive: true, force: true })
    }
  }
  writeFileSync(join(out, 'e2e-library.done'), new Date().toISOString())
}
