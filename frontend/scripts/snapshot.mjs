// Capture de l'interface :
//   node scripts/snapshot.mjs <url> <sortie.png> [--dark] [--width 1440] [--height 900] [--wait 6000]

import { launch, sleep } from './cdp.mjs'

const args = process.argv.slice(2)
const option = (name, fallback) => {
  const index = args.indexOf(name)
  return index >= 0 ? args[index + 1] : fallback
}
const [url, output] = args
const browser = await launch({
  width: Number(option('--width', 1440)),
  height: Number(option('--height', 900)),
  dark: args.includes('--dark'),
})
try {
  await browser.goto(url)
  await sleep(Number(option('--wait', 6000)))
  await browser.screenshot(output)
  console.log([...browser.logs, `capture : ${output}`].join('\n'))
} finally {
  browser.close()
}
