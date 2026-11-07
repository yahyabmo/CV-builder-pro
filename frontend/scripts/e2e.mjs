// Parcours de bout en bout de l'éditeur sur un CV d'essai (cvs/essai-ui) :
// ouverture, rendu de l'aperçu, frappe, sauvegarde, recompilation, annulation.
//
//   node scripts/e2e.mjs <dossier des captures>

import { execFileSync } from 'node:child_process'
import { launch } from './cdp.mjs'
import { APP, DATA } from './e2e-env.mjs'

const out = process.argv[2] ?? '.'
const app = `${APP}/`
const browser = await launch({ init: "localStorage.setItem('cv-builder.selected', 'essai-ui')" })
const check = (ok, text) => console.log(`${ok ? 'ok  ' : 'ÉCHEC'} ${text}`)

// La valeur d'un champ React se change par le setter natif, puis un événement input.
const typeInto = (selector, text) => `(() => {
  const el = ${selector}
  const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value').set
  setter.call(el, el.value + ${JSON.stringify(text)})
  el.dispatchEvent(new Event('input', { bubbles: true }))
  return true
})()`
const summary = `[...document.querySelectorAll('label')].find(l => l.textContent.startsWith('Accroche')).querySelector('textarea')`
const pdfText = () => execFileSync('pdftotext', [`${DATA}/cvs/essai-ui/cv.pdf`, '-'], { encoding: 'utf8' })
const pdfVersion = `document.querySelector('a[download]')?.getAttribute('href')`
// La page devant contient de l'encre : au moins un pixel sombre dans son canevas.
const inked = `(() => { const c = document.querySelector('[data-front=true] canvas'); if (!c) return false; const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; for (let i = 0; i < d.length; i += 4) if (d[i] < 100) return true; return false })()`

try {
  await browser.goto(app)
  const opened = await browser.waitFor(`document.querySelector('h1')?.textContent === 'Essai interface'`)
  check(true, `CV d'essai ouvert en ${opened} ms`)
  const drawn = await browser.waitFor(`[...document.querySelectorAll('canvas')].some(c => c.width > 400 && !c.closest('[aria-hidden=true]'))`, 30000)
  check(true, `première page du PDF dessinée en ${drawn} ms`)
  await browser.screenshot(`${out}/e2e-1-ouvert.png`)

  const before = await browser.evaluate(pdfVersion)
  await browser.evaluate(`${summary}.focus()`)
  await browser.evaluate(typeInto(summary, ' Essai E2E'))
  const started = Date.now()
  // Pendant l'enregistrement et la compilation, l'ancienne page reste affichée.
  const during = []
  for (let t = 0; t < 1200; t += 100) {
    during.push((await browser.evaluate(inked)) ? '█' : '·')
    await new Promise((r) => setTimeout(r, 100))
  }
  console.log('     encre pendant la compilation, toutes les 100 ms :', during.join(''))
  check(during.every((x) => x === '█'), "l'aperçu reste affiché pendant la compilation")
  await browser.waitFor(`document.querySelector('[role=status]')?.textContent.startsWith('Enregistré') && document.querySelector('a[download]')?.getAttribute('href') !== ${JSON.stringify(before)}`, 20000)
  // La page devant doit être celle du dernier PDF (celui du lien de téléchargement).
  const front = `document.querySelector('[data-front=true]')?.dataset.pdf === document.querySelector('a[download]')?.getAttribute('href')`
  const shown = await browser.waitFor(front)
  check(true, `frappe → enregistré, compilé et affiché en ${Date.now() - started} ms (dont ${shown} ms d'affichage)`)
  check(pdfText().includes('Essai E2E'), 'le PDF contient le texte tapé')
  const timeline = []
  for (let t = 0; t < 2000; t += 100) {
    timeline.push((await browser.evaluate(inked)) ? '█' : '·')
    await new Promise((r) => setTimeout(r, 100))
  }
  console.log('     encre de la page devant, toutes les 100 ms :', timeline.join(''))
  check(timeline.every((x) => x === '█'), 'la page affichée est dessinée sans clignoter')
  await browser.screenshot(`${out}/e2e-2-modifie.png`)

  await browser.key('z', { ctrl: true })
  await browser.waitFor(`!${summary}.value.includes('Essai E2E')`, 5000)
  await browser.waitFor(`document.querySelector('[role=status]')?.textContent.startsWith('Enregistré')`, 20000)
  await browser.waitFor(front)
  check(!pdfText().includes('Essai E2E'), 'Ctrl+Z annule la frappe, et le PDF suit')
  await browser.screenshot(`${out}/e2e-3-annule.png`)

  const errors = browser.logs.filter((l) => /EXCEPTION|console.error/.test(l))
  check(errors.length === 0, `aucune erreur JavaScript${errors.length ? ' : ' + errors.join(' | ') : ''}`)
} catch (error) {
  check(false, error.message)
  console.log(browser.logs.join('\n'))
  process.exitCode = 1
} finally {
  browser.close()
}
