// Parcours de la phase 6 sur un CV d'essai : onglet LaTeX (Monaco), passage
// en mode manuel (confirmation, bandeau, contenu verrouillé), erreur LaTeX
// signalée à sa ligne, retour au mode visuel, onglet ATS, palette Ctrl+K.
//
//   node scripts/e2e-latex.mjs <dossier des captures>

import { existsSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { launch, sleep } from './cdp.mjs'
import { API, APP, DATA } from './e2e-env.mjs'

const out = process.argv[2] ?? '.'
const created = await (await fetch(`${API}/api/cvs`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: 'Essai LaTeX' }) })).json()
const SLUG = created.slug

const browser = await launch({ height: 950 })
const check = (ok, text) => console.log(`${ok ? 'ok  ' : 'ÉCHEC'} ${text}`)
const byText = (selector, text) => `[...document.querySelectorAll('${selector}')].find(e => e.textContent.trim().startsWith(${JSON.stringify(text)}))`
const click = (js) => browser.evaluate(`(() => { const el = ${js}; if (!el) throw new Error('introuvable : ' + ${JSON.stringify(js)}); el.click(); return true })()`)
const tab = (label) => browser.evaluate(`(() => { const t = ${byText('[role=tab]', label)}; t.dispatchEvent(new MouseEvent('mousedown', {bubbles: true})); t.click(); return true })()`)
const bodyHas = (text) => `document.body.innerText.includes(${JSON.stringify(text)})`
const meta = async () => (await (await fetch(`${API}/api/cvs/${SLUG}`)).json()).meta
// Écrire en tête du code, dans Monaco, comme au clavier.
const typeAtTop = async (text) => {
  await browser.evaluate(`document.querySelector('.monaco-editor textarea').focus()`)
  await browser.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Home', code: 'Home', windowsVirtualKeyCode: 36, modifiers: 2 })
  await browser.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Home', code: 'Home', windowsVirtualKeyCode: 36, modifiers: 2 })
  await browser.send('Input.insertText', { text })
  await sleep(300)
}

try {
  await browser.goto(`${APP}/#/cv/${SLUG}`)
  await browser.waitFor(`document.querySelector('h1')?.textContent === 'Essai LaTeX'`)
  await browser.waitFor(`document.querySelector('[data-front=true] canvas')?.width > 400`, 30000)

  // ─── Onglet LaTeX ───
  await tab('LaTeX')
  await browser.waitFor(`document.querySelector('.monaco-editor .view-lines')?.textContent.includes('documentclass')`, 30000)
  check(await browser.evaluate(`!!document.querySelector('.monaco-editor .mtk1, .monaco-editor [class*="mtk"]')`), 'éditeur Monaco affiché, code coloré')
  check(await browser.evaluate(bodyHas('généré')), 'code généré depuis le contenu (mode visuel)')

  // Modifier puis compiler : confirmation, puis mode manuel.
  await typeAtTop('% retouche manuelle\n')
  await click(byText('button', 'Compiler'))
  await browser.waitFor(`document.querySelector('[role=alertdialog]')?.textContent.includes('mode manuel')`)
  check(true, 'passage en mode manuel demandé avant de compiler')
  await click(byText('[role=alertdialog] button', 'Passer en mode manuel'))
  await browser.waitFor(bodyHas('Mode manuel.'), 30000)
  const source = await (await fetch(`${API}/api/cvs/${SLUG}/source`)).json()
  check((await meta()).mode === 'manual' && source.tex.startsWith('% retouche manuelle'), 'mode manuel : le .tex modifié est la source')
  await sleep(500)
  await browser.screenshot(`${out}/latex-manuel.png`)

  // Erreur LaTeX : signalée à sa ligne, dans la liste et dans le code.
  await typeAtTop('\\commandeinconnue\n')
  await click(byText('button', 'Compiler'))
  await browser.waitFor(`document.querySelector('[aria-label="Erreurs LaTeX"]')?.textContent.includes('ligne 1')`, 30000)
  check(await browser.evaluate(`!!document.querySelector('[aria-label="Erreurs LaTeX"]')?.textContent.includes('Commande inconnue')`), 'erreur LaTeX lisible, avec sa ligne')
  await browser.waitFor(`!!document.querySelector('.monaco-editor .squiggly-error')`, 5000)
  check(true, 'erreur soulignée dans le code')
  await browser.screenshot(`${out}/latex-erreur.png`)

  // Contenu verrouillé en mode manuel.
  await tab('Contenu')
  await browser.waitFor(`document.querySelector('fieldset[disabled]')`)
  check(true, 'contenu et style verrouillés en mode manuel')

  // Retour au mode visuel, après confirmation.
  await click(byText('button', 'Revenir au mode visuel'))
  await browser.waitFor(`document.querySelector('[role=alertdialog]')?.textContent.includes('seront perdues')`)
  await click(byText('[role=alertdialog] button', 'Revenir au mode visuel'))
  await browser.waitFor(`!${bodyHas('Mode manuel.')}`, 30000)
  await browser.waitFor(`!document.querySelector('fieldset[disabled]')`)
  check((await meta()).mode === 'visual', 'retour au mode visuel : contenu de nouveau modifiable')

  // ─── Onglet ATS ───
  await tab('ATS')
  await browser.waitFor(bodyHas('Ce que lit un logiciel de tri'), 20000)
  check(await browser.evaluate(bodyHas('Polices intégrées')) && await browser.evaluate(bodyHas('Pas de ligatures')), 'vérifications ATS affichées')
  await browser.evaluate(`(() => { const el = document.querySelector('input[aria-label="Mots-clés à chercher dans le PDF"]'); const set = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value').set; set.call(el, 'Python, Kubernetes'); el.dispatchEvent(new Event('input', {bubbles: true})); return true })()`)
  await click(byText('button', 'Chercher'))
  await browser.waitFor(`[...document.querySelectorAll('span')].some(s => s.textContent === 'Kubernetes' && s.className.includes('line-through'))`, 10000)
  check(await browser.evaluate(`[...document.querySelectorAll('span')].some(s => s.textContent === 'Python' && s.className.includes('success'))`), 'mots-clés cherchés dans le PDF : Python trouvé, Kubernetes absent')
  await browser.screenshot(`${out}/ats.png`)

  // ─── Palette Ctrl+K ───
  await browser.key('k', { ctrl: true })
  await browser.waitFor(`document.querySelector('[cmdk-input]')`)
  await browser.evaluate(`document.querySelector('[cmdk-input]').focus()`)
  await browser.send('Input.insertText', { text: 'code latex' })
  await sleep(200)
  await browser.screenshot(`${out}/palette.png`)
  await browser.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 })
  await browser.waitFor(`${byText('[role=tab]', 'LaTeX')}?.getAttribute('aria-selected') === 'true'`)
  check(true, 'palette : « code latex » ouvre l’onglet LaTeX')
  await browser.key('k', { ctrl: true })
  await browser.waitFor(`document.querySelector('[cmdk-input]')`)
  await browser.evaluate(`document.querySelector('[cmdk-input]').focus()`)
  await browser.send('Input.insertText', { text: 'bibliot' })
  await sleep(200)
  await browser.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 })
  await browser.waitFor(`location.hash === '#/library'`)
  check(true, 'palette : aller à la bibliothèque')

  const errors = browser.logs.filter((l) => /EXCEPTION|console.error/.test(l))
  check(errors.length === 0, `aucune erreur JavaScript${errors.length ? ' : ' + errors.join(' | ') : ''}`)
} catch (error) {
  check(false, error.message)
  await browser.screenshot(`${out}/e2e-latex-echec.png`).catch(() => undefined)
  console.log(browser.logs.join('\n'))
  process.exitCode = 1
} finally {
  browser.close()
  await fetch(`${API}/api/cvs/${SLUG}`, { method: 'DELETE' }).catch(() => undefined)
  rmSync(`${DATA}/cvs/${SLUG}`, { recursive: true, force: true })
  if (existsSync(`${DATA}/corbeille`))
    for (const entry of readdirSync(`${DATA}/corbeille`))
      if (entry.startsWith(`${SLUG}-`)) rmSync(`${DATA}/corbeille/${entry}`, { recursive: true, force: true })
  writeFileSync(join(out, 'e2e-latex.done'), new Date().toISOString())
}
