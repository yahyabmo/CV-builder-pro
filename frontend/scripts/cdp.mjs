// Pilote minimal de Chrome sans affichage par le protocole DevTools, pour les
// vérifications de l'interface (scripts/snapshot.mjs, scripts/e2e.mjs).

import { spawn } from 'node:child_process'
import { mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

export const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

export async function launch({ width = 1440, height = 900, dark = false, init = '' } = {}) {
  const port = 9300 + Math.floor(Math.random() * 500)
  const profile = mkdtempSync(join(tmpdir(), 'cdp-'))
  const chrome = spawn(
    'google-chrome',
    ['--headless=new', '--no-first-run', `--user-data-dir=${profile}`, `--remote-debugging-port=${port}`, 'about:blank'],
    { stdio: 'ignore' },
  )
  let page
  for (let i = 0; i < 50 && !page; i++) {
    try {
      page = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((t) => t.type === 'page')
    } catch {
      /* Chrome démarre */
    }
    if (!page) await sleep(200)
  }
  if (!page) throw new Error('Chrome ne répond pas')
  const socket = new WebSocket(page.webSocketDebuggerUrl)
  await new Promise((resolve) => socket.addEventListener('open', resolve))

  let id = 0
  const pending = new Map()
  const logs = []
  socket.addEventListener('message', (event) => {
    const message = JSON.parse(event.data)
    if (message.id && pending.has(message.id)) {
      pending.get(message.id)(message)
      pending.delete(message.id)
    } else if (message.method === 'Runtime.consoleAPICalled') {
      const text = message.params.args.map((a) => a.value ?? a.description ?? '').join(' ')
      if (!/\[vite\]|React DevTools/.test(text)) logs.push(`console.${message.params.type}: ${text}`)
    } else if (message.method === 'Runtime.exceptionThrown') {
      const d = message.params.exceptionDetails
      logs.push(`EXCEPTION: ${d.exception?.description ?? d.text}`)
    }
  })
  const send = (method, params = {}) =>
    new Promise((resolve) => {
      id += 1
      pending.set(id, resolve)
      socket.send(JSON.stringify({ id, method, params }))
    })

  await send('Runtime.enable')
  await send('Page.enable')
  await send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false })
  await send('Emulation.setEmulatedMedia', {
    features: [{ name: 'prefers-color-scheme', value: dark ? 'dark' : 'light' }],
  })
  if (init) await send('Page.addScriptToEvaluateOnNewDocument', { source: init })

  const evaluate = async (expression) => {
    const answer = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })
    if (answer.result?.exceptionDetails) throw new Error(answer.result.exceptionDetails.exception?.description)
    return answer.result?.result?.value
  }
  return {
    logs,
    send,
    evaluate,
    goto: (url) => send('Page.navigate', { url }),
    async waitFor(expression, timeout = 20000) {
      const start = Date.now()
      while (Date.now() - start < timeout) {
        // !!(…) : un élément du DOM ne se transmet pas, un booléen si.
        if (await evaluate(`!!(${expression})`)) return Date.now() - start
        await sleep(100)
      }
      throw new Error(`délai dépassé : ${expression}`)
    },
    async key(key, { ctrl = false, shift = false } = {}) {
      const modifiers = (ctrl ? 2 : 0) | (shift ? 8 : 0)
      const code = `Key${key.toUpperCase()}`
      const keyCode = key.toUpperCase().charCodeAt(0)
      await send('Input.dispatchKeyEvent', { type: 'keyDown', key, code, modifiers, windowsVirtualKeyCode: keyCode })
      await send('Input.dispatchKeyEvent', { type: 'keyUp', key, code, modifiers, windowsVirtualKeyCode: keyCode })
    },
    async screenshot(file) {
      const shot = await send('Page.captureScreenshot', { format: 'png' })
      writeFileSync(file, Buffer.from(shot.result.data, 'base64'))
    },
    close() {
      socket.close()
      chrome.kill()
    },
  }
}
