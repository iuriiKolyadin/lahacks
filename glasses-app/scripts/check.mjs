// Opens the built app in headless Chrome (desktop, no glasses), waits for the
// model self-test, and prints the app log. Exit code 1 if the model failed.
//   npm run check
import { spawn, spawnSync } from 'node:child_process'
import { chromium } from 'playwright-core'

const PORT = 4173
const server = spawn(`npx vite preview --port ${PORT} --strictPort`, { shell: true, stdio: 'pipe' })
await new Promise((resolve, reject) => {
  server.stdout.on('data', d => /Local:/.test(String(d)) && resolve())
  server.on('exit', code => reject(new Error(`vite preview exited (${code})`)))
})

let failed = true
const browser = await chromium.launch({ channel: 'chrome', headless: true })
try {
  const page = await browser.newPage()
  page.on('pageerror', e => console.log(`[pageerror] ${e.message}`))
  await page.goto(`http://localhost:${PORT}/`)
  await page.waitForFunction(() => /self-test top|model\] FAILED/.test(window.earshotLog?.() ?? ''), null, { timeout: 60000 })
  const text = await page.evaluate(() => window.earshotLog())
  console.log(text)
  failed = /model\] FAILED/.test(text)
} finally {
  await browser.close()
  if (process.platform === 'win32') spawnSync('taskkill', ['/pid', String(server.pid), '/t', '/f'])
  else server.kill()
}
process.exit(failed ? 1 : 0)
