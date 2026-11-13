// Parcours du premier lancement : l'écran de démarrage (modèle d'IA, clé, machine)
// s'ouvre d'abord, puis l'accueil ; l'import du PDF
// d'exemple (mode démo, sans clé), la relecture (PDF d'origine, retouche,
// élément modifié, aperçu au format de l'appli), la validation ; puis la saisie
// à la main, du nom à la dernière étape ; enfin la clé supprimée dans Réglages.
//
// Il tourne sur les données d'essai de make e2e, et remet les réglages tels quels.
//
//   node scripts/e2e-welcome.mjs <dossier des captures>

import { existsSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { createServer } from 'node:http'
import { join } from 'node:path'
import { launch, sleep } from './cdp.mjs'
import { API, APP, DATA, LOCAL } from './e2e-env.mjs'

const out = process.argv[2] ?? '.'

// Un faux relais de Yahya (port 8002, voir run-e2e.sh) : il reconnaît un seul code.
const RELAY_CODE = 'cvb-essa-iess-aies-saie'
const relay = createServer((request, response) => {
  const known = request.headers.authorization === `Bearer ${RELAY_CODE}`
  response.writeHead(known ? 200 : 401, { 'content-type': 'application/json' })
  response.end(
    JSON.stringify(
      known
        ? { ok: true, nom: 'Essai', reste_jour: 20, quota_jour: 20, credit_epuise: false, modele: 'gemini-3.5-flash-lite' }
        : { error: { code: 401, message: 'Code inconnu', status: 'CODE' } },
    ),
  )
}).listen(8002, '127.0.0.1')
const SETTINGS = `${LOCAL}/settings.json`
const savedSettings = existsSync(SETTINGS) ? readFileSync(SETTINGS, 'utf8') : null

const browser = await launch({ height: 950 })
const check = (ok, text) => console.log(`${ok ? 'ok  ' : 'ÉCHEC'} ${text}`)
const byText = (selector, text) => `[...document.querySelectorAll('${selector}')].find(e => e.textContent.trim().startsWith(${JSON.stringify(text)}))`
const click = (js) => browser.evaluate(`(() => { const el = ${js}; if (!el) throw new Error('introuvable : ' + ${JSON.stringify(js)}); el.click(); return true })()`)
const type = (js, text) =>
  browser.evaluate(`(() => { const el = ${js}; const set = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value').set; set.call(el, ${JSON.stringify(text)}); el.dispatchEvent(new Event('input', {bubbles: true})); return true })()`)
// Un menu Radix s'ouvre au pointeur, pas au simple clic.
const press = (js) =>
  browser.evaluate(`(() => { const el = ${js}; if (!el) throw new Error('introuvable : ' + ${JSON.stringify(js)}); el.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true, button: 0, pointerType: 'mouse'})); return true })()`)
const bodyHas = (text) => `document.body.innerText.includes(${JSON.stringify(text)})`
const labelled = (label) => `[...document.querySelectorAll('label')].find(l => l.firstChild?.textContent?.trim() === ${JSON.stringify(label)})?.querySelector('input, textarea')`
const base = async () => (await (await fetch(`${API}/api/cvs/base`)).json()).content
const reopen = () => {
  const file = `${DATA}/base/meta.json`
  writeFileSync(file, JSON.stringify({ ...JSON.parse(readFileSync(file, 'utf8')), welcome: true }))
}

try {
  // ─── L'écran de démarrage vient d'abord, tant qu'il n'a pas été passé ───
  writeFileSync(SETTINGS, JSON.stringify({ ...(savedSettings ? JSON.parse(savedSettings) : {}), provider: 'gemini' }))
  rmSync(`${LOCAL}/setup.json`, { force: true })
  reopen()
  await browser.goto(`${APP}/#/cvs`)
  await browser.waitFor(bodyHas("Réglons l'essentiel avant de commencer."), 10000)
  await browser.waitFor(`document.querySelectorAll('ul[aria-label="Vérifications de la machine"] li').length === 4`, 15000)
  check(
    await browser.evaluate(`location.hash === '#/welcome/setup' && document.querySelectorAll('[role=radio]').length === 3 && ${bodyHas('Clé enregistrée')}`),
    'démarrage ouvert d’abord : trois choix, la clé Gemini trouvée, la machine vérifiée',
  )
  const next = byText('button', 'Continuer vers mon CV de base')
  await click(byText('button', 'Mistral'))
  await browser.waitFor(bodyHas("Ajoute d'abord ta clé Mistral."), 5000)
  const keyField = `document.getElementById([...document.querySelectorAll('label')].find(l => l.textContent.trim() === "Clé d'API Mistral").htmlFor)`
  await type(keyField, 'pas une clé')
  await click(`[...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Vérifier')`)
  await browser.waitFor(bodyHas("Ça ne ressemble pas à une clé d'API"), 5000)
  check(await browser.evaluate(`${next}.disabled`), 'Mistral sans clé : « Continuer » bloqué, une clé mal collée refusée sans appel')
  // Gemini de Yahya : un code inconnu est refusé, le bon est vérifié par le relais puis rangé dans .env.
  await click(`[...document.querySelectorAll('[role=radio]')].find(e => e.textContent.includes('Gemini de Yahya'))`)
  await browser.waitFor(bodyHas("Ajoute d'abord ton code d'accès."), 5000)
  const codeField = `document.getElementById([...document.querySelectorAll('label')].find(l => l.textContent.trim() === "Code d'accès").htmlFor)`
  const verify = `[...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Vérifier')`
  await type(codeField, 'cvb-faux-faux-faux-faux')
  await click(verify)
  await browser.waitFor(bodyHas("n'est pas reconnu"), 5000)
  const refused = !readFileSync(`${LOCAL}/.env`, 'utf8').includes('RELAIS_CODE') && (await browser.evaluate(`${next}.disabled`))
  await type(codeField, RELAY_CODE)
  await click(verify)
  await browser.waitFor(bodyHas('Code enregistré'), 5000)
  check(
    refused && readFileSync(`${LOCAL}/.env`, 'utf8').includes(`RELAIS_CODE=${RELAY_CODE}`) && !(await browser.evaluate(`${next}.disabled`)),
    'Gemini de Yahya : code inconnu refusé, bon code vérifié par le relais et rangé dans .env',
  )
  await browser.screenshot(`${out}/demarrage.png`)
  await click(byText('button', 'Plus tard : découvrir en mode Démo'))
  await browser.waitFor(bodyHas('Commençons par ton CV de base.'), 10000)
  const after = await (await fetch(`${API}/api/settings`)).json()
  check(
    (await browser.evaluate(`location.hash === '#/welcome'`)) && after.ai.provider === 'demo' && existsSync(`${LOCAL}/setup.json`),
    'mode Démo choisi, démarrage passé : accueil et ses trois choix',
  )
  await browser.screenshot(`${out}/accueil.png`)

  // ─── Import du PDF d'exemple ───
  await click(byText('button', 'Recommandé'))
  await browser.waitFor(bodyHas('Importe ton CV'), 5000)
  await browser.waitFor(bodyHas('Mode démo'), 5000)
  check(true, 'import : mode démo signalé')
  await click(byText('button', "Essayer avec le PDF d'exemple"))
  await browser.waitFor(`location.hash.startsWith('#/welcome/review/') && document.body.innerText.includes("Relis ce que l'appli a repéré")`, 30000)
  await browser.waitFor(`document.querySelector('section[aria-label="Ton PDF d\\'origine"] canvas')?.width > 100`, 20000)
  check(
    await browser.evaluate(`!document.querySelector('[aria-label="Points à vérifier"]') && document.body.innerText.includes('Photo trouvée dans le PDF')`),
    'relecture : PDF d’origine affiché, photo trouvée, rien à vérifier',
  )
  await type(labelled('Titre'), 'Data Science & IA (relu)')
  await click(`[...document.querySelectorAll('button[aria-expanded]')].find(b => b.textContent.includes('EXPÉRIENCE PROFESSIONNELLE'))`)
  await browser.waitFor(byText('button', 'Modifier'), 5000)
  await click(byText('button', 'Modifier'))
  await browser.waitFor(`document.querySelector('textarea[aria-label^="Ce que tu y as fait"]')`, 5000)
  check(true, 'relecture : titre retouché, expérience ouverte en édition')
  await browser.screenshot(`${out}/relecture.png`)

  // La forme : le clone de ton PDF par défaut, sa note, ton PDF et lui superposés.
  await click(byText('[role=radio]', 'Forme'))
  await browser.waitFor(bodyHas('Ressemblance avec ton PDF'), 120000)
  const likeness = await browser.evaluate(`Number(document.querySelector('[aria-label^="Ressemblance"]').getAttribute('aria-label').match(/\\d+/)[0])`)
  await browser.waitFor(`document.querySelectorAll('[aria-label="Ton PDF et le clone superposés"] canvas').length >= 2`, 30000)
  check(likeness >= 80 && (await browser.evaluate(`!!document.querySelector('input[aria-label="Part du clone affichée"]')`)), `clone de ton PDF : ${likeness} % de ressemblance, curseur de comparaison`)
  await browser.screenshot(`${out}/import-clone.png`)

  // « Proche du mien » : le style repéré, élément par élément, et l'aperçu qui le suit.
  await click(byText('[role=radio]', 'Proche du mien'))
  await browser.waitFor(bodyHas('Repéré dans ton PDF'), 15000)
  await browser.waitFor(`[...document.querySelectorAll('canvas')].length >= 2`, 30000)
  check(
    await browser.evaluate(`${bodyHas('PT Serif')} && document.querySelectorAll('input[aria-label^="Reprendre"]:checked').length >= 6`),
    'proche du mien : PT Serif, éléments cochés, aperçu compilé',
  )
  await browser.screenshot(`${out}/import-style.png`)
  await click(byText('[role=radio]', "Style de l'appli"))
  await browser.waitFor(`document.querySelectorAll('canvas').length >= 2`, 30000)
  check(true, "style de l'appli : aperçu compilé")
  await click(byText('[role=radio]', 'Identique au mien'))
  await click(byText('[role=radio]', 'Rubriques'))

  await click(byText('button', 'Valider ce CV'))
  await browser.waitFor(bodyHas('Ton CV classique est prêt'), 30000)
  const imported = await base()
  const status = await (await fetch(`${API}/api/welcome`)).json()
  check(imported.header.headline === 'Data Science & IA (relu)' && imported.header.photo === 'photo.jpg' && !status.show, 'CV validé : retouche gardée, photo reprise, accueil refermé')
  const source = (await (await fetch(`${API}/api/cvs/base/source`)).json()).tex
  check(source.includes('CV cloné') && source.includes('PTSerif'), 'CV de base validé en clone : la forme du PDF, en PT Serif')
  const library = await (await fetch(`${API}/api/library`)).json()
  check(library.skills.length > 15 && library.projects.length >= 4, `bibliothèque remplie (${library.skills.length} compétences, ${library.projects.length} projets)`)
  await browser.screenshot(`${out}/accueil-fin.png`)
  await click(byText('button', 'Ajuster le style'))
  await browser.waitFor(`location.hash === '#/cv/base'`, 5000)
  check(true, '« Ajuster le style » ouvre le CV de base')

  // La forme du CV cloné, dans l'onglet Style : la mise en page de l'appli, puis retour au clone.
  const tex = async () => (await (await fetch(`${API}/api/cvs/base/source`)).json()).tex
  await browser.waitFor(byText('[role=tab]', 'Style'), 10000)
  await browser.evaluate(`(() => { const t = ${byText('[role=tab]', 'Style')}; t.dispatchEvent(new MouseEvent('mousedown', {bubbles: true})); t.click(); return true })()`)
  await browser.waitFor(byText('[role=radio]', 'Copie de ton PDF'), 10000)
  check(await browser.evaluate(`${byText('[role=radio]', 'Copie de ton PDF')}.getAttribute('aria-checked') === 'true'`), 'onglet Style : « Forme du CV », la copie du PDF choisie')
  await click(byText('[role=radio]', "Mise en page de l'appli"))
  await browser.waitFor(byText('button', 'Couleurs'), 30000)
  check(!(await tex()).includes('CV cloné'), "forme : la mise en page de l'appli, réglages de style revenus")
  await browser.screenshot(`${out}/forme-appli.png`)
  await click(byText('[role=radio]', 'Copie de ton PDF'))
  await browser.waitFor(`!${byText('button', 'Couleurs')}`, 30000)
  check((await tex()).includes('CV cloné'), 'forme : retour à la copie du PDF, sans réimporter')

  // ─── Saisie à la main, par « Remplacer par un autre… » du menu de ce CV classique ───
  const baseMenu = (name) => `document.querySelector('button[aria-label="Menu de ${name}"]')`
  const menuItem = (text) => `[...document.querySelectorAll('[role=menuitem]')].find(i => i.textContent.includes(${JSON.stringify(text)}))`
  const baseNames = `[...document.querySelectorAll('button[aria-label^="Menu de "]')].map(b => b.getAttribute('aria-label').slice(8))`
  await browser.waitFor(baseMenu('Version classique'), 10000)
  await press(baseMenu('Version classique'))
  await browser.waitFor(menuItem('Remplacer par un autre'), 5000)
  await click(menuItem('Remplacer par un autre'))
  await browser.waitFor(bodyHas('Remplacer « Version classique »'), 5000)
  check(!(await browser.evaluate(bodyHas("Partir de l'exemple"))), 'remplacer un CV classique : sans « Partir de l’exemple »')
  await click(byText('button', 'Le remplir à la main'))
  await browser.waitFor(labelled('Nom et prénom'), 10000)
  await type(labelled('Nom et prénom'), 'Alex Martin')
  await type(labelled('Titre sous le nom'), 'Développement logiciel')
  await type(labelled('Ville'), 'Nantes, France')
  await click(byText('button', 'Suivant'))
  await browser.waitFor(byText('button', 'Ajouter une formation'), 5000)
  await click(byText('button', 'Ajouter une formation'))
  await browser.waitFor(`document.querySelector('input[aria-label^="Diplôme ou formation"]')`, 5000)
  await type(`document.querySelector('input[aria-label^="Diplôme ou formation"]')`, 'Licence informatique')
  await click(`[...document.querySelectorAll('nav[aria-label="Sections"] button')].find(b => b.textContent.includes('Langues et intérêts'))`)
  await browser.waitFor(`document.querySelectorAll('textarea').length > 0 && document.body.innerText.includes('Terminer mon CV')`, 5000)
  await type(`[...document.querySelectorAll('textarea')].pop()`, 'Course à pied\nPiano')
  await sleep(300)
  await click(byText('button', 'Terminer mon CV'))
  await browser.waitFor(bodyHas('Ton CV classique est prêt'), 30000)
  const manual = await base()
  const sections = Object.fromEntries(manual.sections.map((s) => [s.id, s]))
  check(
    manual.header.name === 'Alex Martin' && manual.header.contact_lines[0][0].text === 'Nantes, France' && sections.formation.visible && sections.formation.items.length === 1 && !sections.projets.visible && sections['centres-interet'].items.length === 2,
    'saisie à la main : CV créé, rubriques vides masquées',
  )

  check(await browser.evaluate(bodyHas('Il remplace « Version classique »')), 'message : il remplace ce CV classique')
  await click(byText('button', 'Ajuster le style'))
  await browser.waitFor(`location.hash === '#/cv/base'`, 5000)

  // ─── Un CV classique de plus : « + Ajouter », saisie à la main ───
  await click(`[...document.querySelectorAll('aside button')].find(b => b.textContent.trim() === 'Ajouter')`)
  await browser.waitFor(bodyHas('Un nouveau CV classique'), 5000)
  await type(`document.querySelector('input[placeholder="CV Chef de projet"]')`, 'CV Anglais')
  await click(byText('[role=radio]', 'Le remplir à la main'))
  await click(byText('button', 'Continuer'))
  await browser.waitFor(labelled('Nom et prénom'), 10000)
  await type(labelled('Nom et prénom'), 'Alex Martin')
  await click(`[...document.querySelectorAll('nav[aria-label="Sections"] button')].find(b => b.textContent.includes('Langues et intérêts'))`)
  await browser.waitFor(bodyHas('Terminer mon CV'), 5000)
  await click(byText('button', 'Terminer mon CV'))
  await browser.waitFor(bodyHas("« CV Anglais » s'ajoute à tes CV classiques"), 30000)
  const all = await (await fetch(`${API}/api/cvs`)).json()
  const bases = all.filter((cv) => cv.meta.kind === 'base')
  check(bases.length === 2 && (await base()).header.name === 'Alex Martin', 'nouveau CV classique ajouté, la première version garde son contenu')
  await click(byText('button', 'Ajuster le style'))
  await browser.waitFor(`location.hash === '#/cv/cv-anglais'`, 10000)
  await browser.waitFor(`${baseNames}.length === 2`, 10000)
  check(true, 'deux CV classiques dans la barre de gauche, le nouveau ouvert')

  // Copie, passage de l'un à l'autre, puis corbeille.
  await press(baseMenu('CV Anglais'))
  await browser.waitFor(menuItem('Dupliquer'), 5000)
  await click(menuItem('Dupliquer'))
  await browser.waitFor(`${baseNames}.includes('CV Anglais (copie)')`, 15000)
  await click(`[...document.querySelectorAll('aside button')].find(b => b.textContent.includes('Version classique') && !b.getAttribute('aria-label'))`)
  await browser.waitFor(`location.hash === '#/cv/base'`, 5000)
  check(true, 'copie ajoutée ; clic sur un autre CV classique : il s’ouvre')
  await press(baseMenu('CV Anglais (copie)'))
  await browser.waitFor(menuItem('Supprimer'), 5000)
  await click(menuItem('Supprimer'))
  await browser.waitFor(byText('button', 'Mettre à la corbeille'), 5000)
  await click(byText('button', 'Mettre à la corbeille'))
  await browser.waitFor(`${baseNames}.length === 2 && !${baseNames}.includes('CV Anglais (copie)')`, 10000)
  check(true, 'CV classique mis à la corbeille, les autres restent')
  await browser.screenshot(`${out}/cv-classiques.png`)

  // ─── Réglages : la clé se supprime sans ouvrir .env ───
  await browser.goto(`${APP}/#/settings`)
  await browser.waitFor(bodyHas('Clé enregistrée'), 10000)
  await browser.waitFor(bodyHas('LaTeX, paquets du CV et outils PDF installés.'), 15000)
  check(true, 'Réglages : clé Gemini enregistrée, machine vérifiée')
  // La ligne de « Gemini (ta clé) » : le code du relais, au-dessus, reste en place.
  await click(`[...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Supprimer' && b.closest('.surface')?.textContent.includes('Gemini (ta clé)'))`)
  await click(byText('button', 'Supprimer la clé'))
  await browser.waitFor(`[...document.querySelectorAll('label')].some(l => l.textContent.trim() === "Clé d'API Gemini")`, 5000)
  check(!readFileSync(`${LOCAL}/.env`, 'utf8').includes('GEMINI_API_KEY'), 'clé supprimée de .env, champ pour en ajouter une')

  const errors = browser.logs.filter((l) => /EXCEPTION|console.error/.test(l))
  check(errors.length === 0, `aucune erreur JavaScript${errors.length ? ' : ' + errors.join(' | ') : ''}`)
} catch (error) {
  check(false, error.message)
  await browser.screenshot(`${out}/e2e-welcome-echec.png`).catch(() => undefined)
  console.log(browser.logs.join('\n'))
  process.exitCode = 1
} finally {
  relay.close()
  browser.close()
  if (savedSettings != null) writeFileSync(SETTINGS, savedSettings)
  else rmSync(SETTINGS, { force: true })
  writeFileSync(join(out, 'e2e-welcome.done'), new Date().toISOString())
}
