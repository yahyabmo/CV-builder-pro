// Parcours de l'onglet Style sur le CV d'essai (cvs/essai-ui) : couleur,
// titres en bandeau, taille d'un bloc, Ctrl+Z, import et recadrage de photo.
//
//   node scripts/e2e-style.mjs <dossier des captures> <photo.jpg>

import { readFileSync } from 'node:fs'
import { launch, sleep } from './cdp.mjs'
import { API, APP, DATA } from './e2e-env.mjs'

const [out = '.', photo] = process.argv.slice(2)
const browser = await launch({ height: 1000, init: "localStorage.setItem('cv-builder.selected', 'essai-ui')" })
const check = (ok, text) => console.log(`${ok ? 'ok  ' : 'ÉCHEC'} ${text}`)
const styleJson = () => JSON.parse(readFileSync(`${DATA}/cvs/essai-ui/style.json`, 'utf8'))
const contentJson = () => JSON.parse(readFileSync(`${DATA}/cvs/essai-ui/content.json`, 'utf8'))
const ready = `document.querySelector('[role=status]')?.textContent.startsWith('Enregistré')`
const front = `document.querySelector('[data-front=true]')?.dataset.pdf === document.querySelector('a[download]')?.getAttribute('href')`
const click = (js) => browser.evaluate(`(() => { const el = ${js}; if (!el) throw new Error('introuvable : ' + ${JSON.stringify(js)}); el.click(); return true })()`)
const byText = (selector, text) => `[...document.querySelectorAll('${selector}')].find(e => e.textContent.trim().startsWith(${JSON.stringify(text)}))`
const settle = async () => {
  await sleep(600)
  await browser.waitFor(ready, 20000)
  await browser.waitFor(front, 10000)
}

try {
  await browser.goto(`${APP}/`)
  await browser.waitFor(`document.querySelector('h1')?.textContent === 'Essai interface'`)
  await browser.waitFor(`document.querySelector('[data-front=true] canvas')?.width > 400`, 30000)
  // Onglet Style (Radix réagit au pointeur : on simule mousedown).
  await browser.evaluate(`(() => { const t = ${byText('[role=tab]', 'Style')}; t.dispatchEvent(new MouseEvent('mousedown', {bubbles: true})); t.click(); return true })()`)
  await browser.waitFor(`${byText('button', 'Couleurs')} !== undefined`)
  check(true, 'onglet Style ouvert')

  // Une palette prête (le groupe Couleurs est ouvert par défaut) : ses 8 couleurs,
  // et les dates, puces et liens sans couleur prennent leur rôle.
  check(await browser.evaluate(`document.querySelectorAll('button[aria-label^="Palette "]').length === 30`), '30 palettes prêtes')
  await click(`document.querySelector('button[aria-label="Palette Bordeaux"]')`)
  await settle()
  const bordeaux = styleJson()
  check(
    bordeaux.palette.primary === '6D1B2E' && bordeaux.palette.title_band === 'EFDDE2' && bordeaux.blocks.date.color === 'muted' && bordeaux.lists.bullet_color === 'accent' && bordeaux.links.color === 'link',
    'palette Bordeaux appliquée, dates, puces et liens sur leur rôle',
  )
  await browser.screenshot(`${out}/style-0-palette.png`)

  // Une couleur de la palette, par son code dans le nuancier.
  const setCode = (code) =>
    browser.evaluate(`(() => { const input = document.querySelector('[data-slot=popover-content] input[aria-label="Code de la couleur"]'); const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; set.call(input, ${JSON.stringify(code)}); input.dispatchEvent(new Event('input', {bubbles: true})); return true })()`)
  await click(`document.querySelector('button[aria-label^="Principale : #"]')`)
  await browser.waitFor(`document.querySelector('[data-slot=popover-content] input[aria-label="Code de la couleur"]')`, 5000)
  check(await browser.evaluate(`document.querySelectorAll('[data-slot=popover-content] button[aria-label*=" #"]').length >= 108`), 'nuancier : 12 familles en 8 nuances, et les gris')
  await setCode('8B1E3F')
  await browser.key('Escape')
  await settle()
  check(styleJson().palette.primary === '8B1E3F', 'couleur principale enregistrée (8B1E3F)')

  // Un texte discret trop pâle : l'alerte de lisibilité, puis « Corriger ».
  await click(`document.querySelector('button[aria-label^="Texte discret : #"]')`)
  await browser.waitFor(`document.querySelector('[data-slot=popover-content] input[aria-label="Code de la couleur"]')`, 5000)
  await setCode('C8C8C8')
  await browser.key('Escape')
  await browser.waitFor(`[...document.querySelectorAll('[role=status]')].some(s => s.textContent.includes('Le texte discret'))`, 5000)
  await click(`[...document.querySelectorAll('[role=status]')].find(s => s.textContent.includes('Le texte discret')).querySelector('button')`)
  await settle()
  const muted = styleJson().palette.muted
  check(muted !== 'C8C8C8' && !(await browser.evaluate(`[...document.querySelectorAll('[role=status]')].some(s => s.textContent.includes('Le texte discret'))`)), `texte discret trop pâle signalé puis corrigé (#${muted})`)

  // Titres de rubrique en bandeau.
  await click(byText('button', 'Titres de rubrique'))
  await click(`[...document.querySelectorAll('[role=radio]')].find(e => e.textContent === 'Bandeau')`)
  await settle()
  check(styleJson().section_titles.variant === 'band', 'titres de rubrique en bandeau')
  await browser.screenshot(`${out}/style-1-bandeau.png`)

  // Ctrl+Z annule le bandeau.
  await browser.evaluate('document.activeElement?.blur(); true')
  await browser.key('z', { ctrl: true })
  await settle()
  check(styleJson().section_titles.variant === 'rule', 'Ctrl+Z revient au filet')

  // Taille du nom : + deux fois.
  await click(byText('button', 'Polices et texte'))
  await click(`[...document.querySelectorAll('button')].find(b => b.textContent.startsWith('Nom') && b.getAttribute('aria-expanded') !== null)`)
  const before = styleJson().blocks.name.size
  await click(`[...document.querySelectorAll('button[aria-expanded=true]')].find(b => b.textContent.startsWith('Nom')).parentElement.querySelector('button[aria-label=Augmenter]')`)
  await click(`[...document.querySelectorAll('button[aria-expanded=true]')].find(b => b.textContent.startsWith('Nom')).parentElement.querySelector('button[aria-label=Augmenter]')`)
  await settle()
  check(styleJson().blocks.name.size === before + 1, `taille du nom ${before} → ${styleJson().blocks.name.size} pt`)

  // Une colonne : le CV suit l'ordre du contenu, l'éditeur montre une seule liste.
  await click(byText('button', 'Mise en page'))
  await click(`[...document.querySelectorAll('[role=radio]')].find(e => e.textContent === 'Une colonne')`)
  await settle()
  await browser.evaluate(`(() => { const t = ${byText('[role=tab]', 'Contenu')}; t.dispatchEvent(new MouseEvent('mousedown', {bubbles: true})); t.click(); return true })()`)
  await browser.waitFor(`[...document.querySelectorAll('h2')].some(h => h.textContent === 'Rubriques')`, 5000)
  check(styleJson().columns.layout === 'one' && (await browser.evaluate(`![...document.querySelectorAll('h2')].some(h => h.textContent === 'Colonne de droite')`)), 'une colonne : enregistrée, une seule liste de rubriques')
  const order = contentJson().sections.map((s) => s.column)
  check(order[0] === 'right' && order.lastIndexOf('right') < order.indexOf('left'), `une colonne : la grande colonne d'abord (${contentJson().sections.map((s) => s.id).slice(0, 3).join(', ')}…)`)
  await browser.screenshot(`${out}/style-une-colonne.png`)
  await browser.evaluate(`(() => { const t = ${byText('[role=tab]', 'Style')}; t.dispatchEvent(new MouseEvent('mousedown', {bubbles: true})); t.click(); return true })()`)
  // L'onglet Style se remonte replié : on rouvre « Mise en page ».
  await browser.waitFor(byText('button', 'Mise en page'), 5000)
  if (!(await browser.evaluate(`[...document.querySelectorAll('[role=radio]')].some(e => e.textContent === 'Deux colonnes')`))) await click(byText('button', 'Mise en page'))
  await browser.waitFor(`[...document.querySelectorAll('[role=radio]')].some(e => e.textContent === 'Deux colonnes')`, 5000)
  await click(`[...document.querySelectorAll('[role=radio]')].find(e => e.textContent === 'Deux colonnes')`)
  await settle()
  check(styleJson().columns.layout === 'two', 'retour à deux colonnes')

  // Glisser une rubrique de la colonne de gauche dans celle de droite, à la souris.
  await browser.evaluate(`(() => { const t = ${byText('[role=tab]', 'Contenu')}; t.dispatchEvent(new MouseEvent('mousedown', {bubbles: true})); t.click(); return true })()`)
  await browser.waitFor(`document.querySelector('[data-section="langues"] button[aria-label="Déplacer"]')`, 5000)
  const box = (js) => browser.evaluate(`(() => { const r = (${js}).getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2] })()`)
  await browser.evaluate(`document.querySelector('[data-section="experience"]').scrollIntoView({block: 'center'})`)
  await browser.evaluate(`document.querySelector('[data-section="langues"]').scrollIntoView({block: 'center'})`)
  const [hx, hy] = await box(`document.querySelector('[data-section="langues"] button[aria-label="Déplacer"]')`)
  const mouse = (type, x, y) => browser.send('Input.dispatchMouseEvent', { type, x, y, button: 'left', buttons: type === 'mouseReleased' ? 0 : 1, clickCount: 1 })
  await mouse('mousePressed', hx, hy)
  for (let k = 1; k <= 30; k++) {
    // Vers le bas, jusque sous la première rubrique de la colonne de droite.
    const [tx, ty] = await box(`document.querySelector('[data-section="experience"]')`)
    await mouse('mouseMoved', hx + ((tx - hx) * k) / 30, hy + ((ty + 4 - hy) * k) / 30)
    await sleep(25)
  }
  await sleep(150)
  const [tx, ty] = await box(`document.querySelector('[data-section="experience"]')`)
  await mouse('mouseReleased', tx, ty + 4)
  await settle()
  check(contentJson().sections.find((s) => s.id === 'langues')?.column === 'right', 'glisser-déposer : « Langues » passe dans la colonne de droite')
  await browser.screenshot(`${out}/glisser-colonnes.png`)
  // Le menu fait toujours le chemin inverse.
  await browser.evaluate(`(() => { const el = document.querySelector('[data-section="langues"] button[aria-label="Actions"]'); el.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true, button: 0, pointerType: 'mouse'})); return true })()`)
  await browser.waitFor(byText('[role=menuitem]', 'Passer dans la colonne de gauche'), 5000)
  await click(byText('[role=menuitem]', 'Passer dans la colonne de gauche'))
  await settle()
  check(contentJson().sections.find((s) => s.id === 'langues')?.column === 'left', 'le menu « Passer dans la colonne de gauche » marche toujours')
  await browser.evaluate(`(() => { const t = ${byText('[role=tab]', 'Style')}; t.dispatchEvent(new MouseEvent('mousedown', {bubbles: true})); t.click(); return true })()`)
  await browser.waitFor(byText('button', 'Mise en page'), 5000)

  // Photo : import, recadrage, remplacement.
  if (photo) {
    await click(byText('button', 'Photo'))
    const { root } = (await browser.send('DOM.getDocument')).result
    const { nodeId } = (await browser.send('DOM.querySelector', { nodeId: root.nodeId, selector: 'input[type=file]' })).result
    await browser.send('DOM.setFileInputFiles', { nodeId, files: [photo] })
    await browser.waitFor(`${byText('button', 'Utiliser cette photo')} && !${byText('button', 'Utiliser cette photo')}.disabled`, 10000)
    await browser.screenshot(`${out}/style-2-recadrage.png`)
    await click(byText('button', 'Utiliser cette photo'))
    await browser.waitFor(`[...document.querySelectorAll('li[data-sonner-toast]')].some(t => t.textContent.includes('Photo remplacée'))`, 30000)
    await settle()
    check(contentJson().header.photo === 'photo.jpg', 'photo importée, recadrée et utilisée dans le CV')
  }
  await browser.screenshot(`${out}/style-3-fin.png`)

  // Thème : enregistrer le style courant depuis l'interface, puis le supprimer.
  await click(byText('button', 'Thèmes'))
  await browser.evaluate(`(() => { const input = document.querySelector('input[placeholder^="Nom du thème"]'); const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; set.call(input, 'Essai e2e'); input.dispatchEvent(new Event('input', {bubbles: true})); return true })()`)
  await click(`document.querySelector('input[placeholder^="Nom du thème"]').form.querySelector('button[type=submit]')`)
  await browser.waitFor(`[...document.querySelectorAll('span')].some(e => e.textContent === 'Essai e2e')`, 10000)
  const themes = await (await fetch(`${API}/api/themes`)).json()
  const saved = themes.find((t) => t.name === 'Essai e2e')
  check(saved?.style.palette.primary === '8B1E3F', 'thème enregistré avec le style courant')
  if (saved) await fetch(`${API}/api/themes/${saved.slug}`, { method: 'DELETE' })

  const errors = browser.logs.filter((l) => /EXCEPTION|console.error/.test(l))
  check(errors.length === 0, `aucune erreur JavaScript${errors.length ? ' : ' + errors.join(' | ') : ''}`)
} catch (error) {
  check(false, error.message)
  console.log(browser.logs.join('\n'))
  process.exitCode = 1
} finally {
  browser.close()
}
