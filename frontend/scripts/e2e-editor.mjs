// Parcours de l'éditeur d'un CV ciblé (lot C) : menu replié et gardé, fil
// d'Ariane et statut de la candidature, bande de score et mot-clé ajouté à un
// groupe de compétences, clic sur l'aperçu qui mène au champ (expérience,
// coordonnées), boutons Gras et Lien des coordonnées, sommaire, téléchargement.
//
// Il tourne sur les données d'essai de make e2e, sur un CV qu'il crée et supprime.
//
//   node scripts/e2e-editor.mjs <dossier des captures>

import { execFileSync } from 'node:child_process'
import { copyFileSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { launch, sleep } from './cdp.mjs'
import { API, APP, DATA, LOCAL } from './e2e-env.mjs'

const out = process.argv[2] ?? '.'
const SLUG = 'essai-editeur'
const SETTINGS = `${LOCAL}/settings.json`
const savedSettings = existsSync(SETTINGS) ? readFileSync(SETTINGS, 'utf8') : null
const FOLDER = `${DATA}/cvs/${SLUG}`
const DEMO = '../demo'

// Un CV ciblé sur l'offre d'exemple, comme le laisse « Cibler une offre ».
rmSync(FOLDER, { recursive: true, force: true })
mkdirSync(FOLDER, { recursive: true })
for (const name of ['content.json', 'style.json', 'imgcv.jpg']) copyFileSync(join(DEMO, name), join(FOLDER, name))
writeFileSync(join(FOLDER, 'meta.json'), JSON.stringify({ name: 'Essai éditeur', kind: 'cv', company: 'Nordia', position: 'Stage Data Scientist IA générative' }))
const answers = JSON.parse(readFileSync(join(DEMO, 'reponses-ia.json'), 'utf8'))
writeFileSync(join(FOLDER, 'analysis.json'), JSON.stringify({ draft: 'essai', analysis: answers.OfferAnalysis, plan: answers.TargetPlan }))
copyFileSync(join(DEMO, 'offre-exemple.txt'), join(FOLDER, 'offer.txt'))

const browser = await launch({ height: 950 })
const check = (ok, text) => console.log(`${ok ? 'ok  ' : 'ÉCHEC'} ${text}`)
const byText = (selector, text) => `[...document.querySelectorAll('${selector}')].find(e => e.textContent.trim().startsWith(${JSON.stringify(text)}))`
const click = (js) => browser.evaluate(`(() => { const el = ${js}; if (!el) throw new Error('introuvable : ' + ${JSON.stringify(js)}); el.click(); return true })()`)
// Un menu Radix s'ouvre au pointeur, pas au simple clic.
const press = (js) =>
  browser.evaluate(`(() => { const el = ${js}; if (!el) throw new Error('introuvable : ' + ${JSON.stringify(js)}); el.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true, button: 0, pointerType: 'mouse'})); return true })()`)
const content = async () => (await (await fetch(`${API}/api/cvs/${SLUG}`)).json()).content
const meta = async () => (await (await fetch(`${API}/api/cvs/${SLUG}`)).json()).meta
const saved = `document.querySelector('[role=status]')?.textContent.startsWith('Enregistré')`

// Le centre d'un mot du PDF, en points depuis le haut gauche de la page.
const word = (text) => {
  const xml = execFileSync('pdftotext', ['-bbox', `${FOLDER}/cv.pdf`, '-'], { encoding: 'utf8' })
  const found = [...xml.matchAll(/xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</g)].find((m) => m[5] === text)
  if (!found) throw new Error(`mot absent du PDF : ${text}`)
  return { x: (Number(found[1]) + Number(found[3])) / 2, y: (Number(found[2]) + Number(found[4])) / 2 }
}
// Un clic sur la page affichée, à ce point du PDF.
const clickPdf = ({ x, y }) =>
  browser.evaluate(`(() => {
    const page = document.querySelector('[data-front=true]')
    const box = page.getBoundingClientRect()
    const scale = box.width / 595.28
    const clientX = box.left + ${x} * scale, clientY = box.top + ${y} * scale
    page.scrollIntoView({ block: 'nearest' })
    const after = page.getBoundingClientRect()
    const cx = after.left + ${x} * scale, cy = after.top + ${y} * scale
    document.elementFromPoint(cx, cy).dispatchEvent(new MouseEvent('click', { bubbles: true, clientX: cx, clientY: cy }))
    return [clientX, clientY]
  })()`)

try {
  const compiled = await (await fetch(`${API}/api/cvs/${SLUG}/compile`, { method: 'POST' })).json()
  check(compiled.ok, 'CV ciblé d’essai compilé')

  await browser.goto(`${APP}/#/cv/${SLUG}`)
  await browser.waitFor(`document.querySelector('h1')?.textContent === 'Essai éditeur'`, 15000)
  await browser.waitFor(`document.querySelector('[data-front=true] canvas')?.width > 100`, 30000)

  // ─── Menu replié, gardé au rechargement ───
  await click(`document.querySelector('button[aria-label="Replier le menu"]')`)
  await browser.waitFor(`document.querySelector('aside[aria-label=Menu]').getBoundingClientRect().width < 70`, 3000)
  await browser.goto(`${APP}/#/cv/${SLUG}`)
  await browser.waitFor(`document.querySelector('h1')?.textContent === 'Essai éditeur'`, 15000)
  check(
    await browser.evaluate(`document.querySelector('aside[aria-label=Menu]').getBoundingClientRect().width < 70 && !!document.querySelector('aside button[aria-label="Candidatures"]')`),
    'menu replié en icônes, gardé au rechargement',
  )

  // ─── Fil d'Ariane et statut ───
  check(await browser.evaluate(`!!document.querySelector('nav[aria-label="Fil d\\'Ariane"] a[href="#/cvs"]')`), 'fil d’Ariane vers les candidatures')
  await press(`document.querySelector('button[aria-label^="Statut de la candidature"]')`)
  await browser.waitFor(byText('[role=menuitem]', 'Envoyée'), 5000)
  await click(byText('[role=menuitem]', 'Envoyée'))
  await browser.waitFor(`document.querySelector('button[aria-label="Statut de la candidature : Envoyée"]')`, 5000)
  await sleep(300)
  check((await meta()).application.status === 'sent', 'statut changé depuis l’éditeur, enregistré')

  // ─── Bande de score : un mot-clé absent ajouté à un groupe de compétences ───
  await browser.waitFor(`document.querySelector('[role=region][aria-label="Correspondance à l\\'offre"]')?.textContent.includes('%')`, 15000)
  const chip = `[...document.querySelectorAll('[role=region][aria-label="Correspondance à l\\'offre"] button')].find(b => b.querySelector('svg') && !b.textContent.startsWith('Voir'))`
  const term = await browser.evaluate(`${chip}?.textContent.trim() ?? ''`)
  if (term) {
    await click(chip)
    await browser.waitFor(bodyHas('L\'ajouter à un groupe de compétences'), 5000)
    await click(`[...document.querySelectorAll('[data-slot=popover-content] button')][0]`)
    await browser.waitFor(saved, 20000)
    const skills = (await content()).sections.filter((s) => s.kind === 'skills').flatMap((s) => s.items.map((i) => i.text))
    check(skills.some((text) => text.includes(term)), `mot-clé « ${term} » ajouté à un groupe de compétences`)
    await browser.waitFor(`document.activeElement?.closest('[data-item^="competences/"]')`, 5000)
    check(true, 'le champ du groupe est ouvert et prêt à la frappe')
  } else check(await browser.evaluate(bodyHas('Tous les mots-clés')), 'aucun mot-clé absent')
  await browser.screenshot(`${out}/editeur-score.png`)

  // ─── Clic sur l'aperçu : l'expérience, puis une coordonnée ───
  await browser.waitFor(saved, 20000)
  await browser.waitFor(`document.querySelector('[data-front=true] canvas')?.width > 100`, 30000)
  await sleep(500)
  await clickPdf(word('Logistica'))
  await browser.waitFor(`document.querySelector('[data-item="experience/0"]') && document.activeElement?.closest('[data-item="experience/0"]')`, 8000)
  check(
    await browser.evaluate(`!!document.querySelector('[data-item="experience/0"][data-flash]') && document.querySelector('nav[aria-label=Sommaire] [aria-current=location]')?.textContent.startsWith('Expérience')`),
    'clic sur l’aperçu : expérience ouverte, entourée, curseur dans son champ, sommaire à jour',
  )
  check(await browser.evaluate(`!!document.querySelector('.ring-2.ring-primary\\\\/70')`), 'élément entouré sur l’aperçu')
  await browser.screenshot(`${out}/editeur-clic.png`)
  await sleep(2000)
  await clickPdf(word('Téléphone'))
  await browser.waitFor(`document.querySelector('[data-block="contact/0"][data-flash]')`, 8000)
  check(true, 'clic sur une coordonnée : sa ligne entourée')

  // ─── Coordonnées : Gras et Lien ───
  const bold = `document.querySelector('[data-block="contact/0"] button[aria-label="Texte en gras"]')`
  const before = (await content()).header.contact_lines[0][0].bold
  await click(bold)
  await browser.waitFor(`${bold}.getAttribute('aria-pressed') === ${JSON.stringify(String(!before))}`, 3000)
  await browser.waitFor(saved, 20000)
  check(Boolean((await content()).header.contact_lines[0][0].bold) === !before, 'bouton Gras : état visible et enregistré')
  await click(`document.querySelector('[data-block="contact/0"] button[aria-label="Ajouter un lien"]')`)
  await browser.waitFor(bodyHas('Adresse du lien'), 3000)
  check(true, 'bouton Lien : champ d’adresse ouvert')

  // ─── Sommaire ───
  await click(byText('nav[aria-label=Sommaire] button', 'Langues'))
  await browser.waitFor(`document.querySelector('[data-section="langues"] [data-item="langues/0"]')`, 5000)
  check(true, 'sommaire : la rubrique s’ouvre')

  // ─── Idées de projet, en mode démo ───
  const real = await (await fetch(`${API}/api/settings`)).json()
  mkdirSync(LOCAL, { recursive: true })
  writeFileSync(SETTINGS, JSON.stringify({ ...real.ai, provider: 'demo' }))
  await browser.evaluate(`(() => { const t = ${byText('[role=tab]', 'Offre')}; t.dispatchEvent(new MouseEvent('mousedown', {bubbles: true})); t.click(); return true })()`)
  await browser.waitFor(byText('button', 'Proposer 3 idées'), 15000)
  await click(byText('button', 'Proposer 3 idées'))
  await browser.waitFor(`document.querySelectorAll('section[aria-label="Idées de projet"] article').length === 3`, 20000)
  await click(byText('button', 'Voir le cahier des charges'))
  await browser.waitFor(`document.querySelector('[data-slot=sheet-content]')?.textContent.includes('Étapes')`, 5000)
  check(
    await browser.evaluate(`document.querySelector('[data-slot=sheet-content] a[download]')?.getAttribute('href').endsWith('/project-ideas/0/brief')`),
    'idées de projet : trois idées, cahier des charges ouvert et téléchargeable',
  )
  await browser.screenshot(`${out}/idees-projet.png`)
  await browser.key('Escape')
  await browser.waitFor(`!document.querySelector('[data-slot=sheet-content]')`, 5000)

  // ─── Téléchargement ───
  await press(byText('button', 'Télécharger'))
  await browser.waitFor(byText('[role=menuitem]', 'Le CV en PDF'), 5000)
  check(
    await browser.evaluate(`${byText('[role=menuitem]', 'Le CV en PDF')}.getAttribute('href').includes('/pdf') && ${byText('[role=menuitem]', 'Son code LaTeX')}.getAttribute('download').endsWith('.tex')`),
    'menu Télécharger : PDF et code LaTeX',
  )
  await browser.key('Escape')
  // La dernière modification compilée avant de supprimer le CV d'essai.
  await browser.waitFor(saved, 20000)
  await browser.screenshot(`${out}/editeur.png`)

  const errors = browser.logs.filter((l) => /EXCEPTION|console.error/.test(l))
  check(errors.length === 0, `aucune erreur JavaScript${errors.length ? ' : ' + errors.join(' | ') : ''}`)
} catch (error) {
  check(false, error.message)
  await browser.screenshot(`${out}/e2e-editor-echec.png`).catch(() => undefined)
  console.log(browser.logs.join('\n'))
  process.exitCode = 1
} finally {
  browser.close()
  if (savedSettings != null) writeFileSync(SETTINGS, savedSettings)
  else rmSync(SETTINGS, { force: true })
  await fetch(`${API}/api/cvs/${SLUG}`, { method: 'DELETE' }).catch(() => undefined)
  rmSync(FOLDER, { recursive: true, force: true })
  writeFileSync(join(out, 'e2e-editor.done'), new Date().toISOString())
}

function bodyHas(text) {
  return `document.body.innerText.includes(${JSON.stringify(text)})`
}
