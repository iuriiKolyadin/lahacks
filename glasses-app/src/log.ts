// One logger for everything. Lines go to the browser console (visible in the
// Even app's Developer Mode console and in desktop DevTools) and to the log
// panel on the phone page. The last LINES lines are kept for `dumpLog()`.
const LINES = 500
const lines: string[] = []
let panel: HTMLElement | null = null

const t0 = performance.now()

export function log(tag: string, ...parts: unknown[]) {
  const t = ((performance.now() - t0) / 1000).toFixed(2).padStart(7)
  const text = parts.map(p => (typeof p === 'string' ? p : JSON.stringify(p))).join(' ')
  const line = `${t} [${tag}] ${text}`
  console.log(line)
  lines.push(line)
  if (lines.length > LINES) lines.shift()
  panel ??= document.getElementById('log')
  if (panel) {
    panel.textContent = lines.slice(-80).join('\n')
    panel.scrollTop = panel.scrollHeight
  }
}

export function dumpLog(): string {
  return lines.join('\n')
}

// Exposed for the headless test runner and for typing `earshotLog()` into a console.
;(window as unknown as { earshotLog: () => string }).earshotLog = dumpLog
