// Draws a HudState (PLAN.md section 3) on the glasses.
//
// One full-screen text container, updated only with textContainerUpgrade,
// brightness via textColor, at least 150 ms between writes (only the latest
// pending state is written; older ones are dropped, never queued).
//
// The G2 is monochrome green, so the wearer's alert tiers (settings.ts) are
// drawn with brightness, flashing and case instead of colour. The server's
// `level` field is ignored; the tier decides.
//
// The firmware font is proportional and its glyph widths are not published,
// so centering is an estimate: CHAR_PX below, scaled by ?scale=, with the
// line height from ?line=. Tune both on the real glasses with ?demo=1.

import {
  TextContainerProperty,
  TextContainerUpgrade,
  type EvenAppBridge,
} from '@evenrealities/even_hub_sdk'
import type { HudState } from './link'
import { tierOf, onTiersChanged, type Tier } from './settings'

const ID = 1
const NAME = 'hud'
const WIDTH = 576
const HEIGHT = 288
const PADDING = 4
const MIN_WRITE_GAP_MS = 150
const SPEECH_MIN_MS = 1000
const FLASH_MS = 300 // urgent: alternate bright and dim this often
const LEVEL: Record<Tier, number> = { urgent: 4, important: 4, normal: 2 }
const FLASH_DIM = 1

const params = new URLSearchParams(location.search)
const SCALE = Number(params.get('scale') ?? 1)
const LINE_PX = Number(params.get('line') ?? 32)

// Rough glyph widths in px for the firmware font; only the ratio matters, ?scale= fixes the size.
function charPx(c: string): number {
  if (c === ' ') return 6
  if ('il.,:;|!\'()[]'.includes(c)) return 7
  if ('-'.includes(c)) return 9
  if ('<>'.includes(c)) return 13
  if ('MW'.includes(c)) return 20
  if (c >= 'A' && c <= 'Z') return 16
  if ('mw'.includes(c)) return 18
  if ('frtj'.includes(c)) return 8
  return 12
}

function textPx(s: string): number {
  let px = 0
  for (const c of s) px += charPx(c)
  return px * SCALE
}

function centerLine(s: string): string {
  const free = WIDTH - 2 * PADDING - textPx(s)
  const spaces = Math.max(0, Math.floor(free / 2 / (charPx(' ') * SCALE)))
  return ' '.repeat(spaces) + s
}

function centerBlock(lines: string[]): string {
  const rows = Math.floor((HEIGHT - 2 * PADDING) / LINE_PX)
  const top = Math.max(0, Math.floor((rows - lines.length) / 2))
  return '\n'.repeat(top) + lines.map(centerLine).join('\n')
}

// Arrow lines point where the sound came from: a horizontal line beside the
// label for left and right, a vertical one above (front) or below (behind) it.
// near has none. ASCII only: the firmware font's other glyphs are unverified.
const ARROW_LEFT = '<-----'
const ARROW_RIGHT = '----->'
const ARROW_UP = ['^', '|']
const ARROW_DOWN = ['|', 'v']

// Display text for a label; the server's ids are short.
const SHOW: Partial<Record<NonNullable<HudState['label']>, string>> = { clap: 'clapping', snap: 'snap' }

function withDir(label: string, dir: HudState['dir']): string[] {
  switch (dir) {
    case 'left': return [`${ARROW_LEFT}  ${label}`]
    case 'right': return [`${label}  ${ARROW_RIGHT}`]
    case 'front': return [...ARROW_UP, label]
    case 'behind': return [label, ...ARROW_DOWN]
    default: return [label]
  }
}

function dirOnly(dir: HudState['dir']): string[] {
  switch (dir) {
    case 'left': return [ARROW_LEFT]
    case 'right': return [ARROW_RIGHT]
    case 'front': return ARROW_UP
    case 'behind': return ARROW_DOWN
    default: return []
  }
}

/** Which tier a state is drawn at. */
export function tierFor(s: HudState): Tier {
  switch (s.state) {
    case 'cue': return tierOf(s.label)
    case 'speech': return tierOf('speech')
    case 'name': return tierOf('name')
    case 'alarm': return tierOf(s.label === 'siren' ? 'siren' : 'alarm')
    default: return 'normal'
  }
}

/** The exact lines for a state, before centering. Empty array means blank. */
export function linesFor(s: HudState): string[] {
  const caps = (t: string) => (tierFor(s) === 'normal' ? t : t.toUpperCase())
  switch (s.state) {
    case 'cue': return withDir(caps((s.label && SHOW[s.label]) ?? s.label ?? ''), s.dir)
    case 'speech': return withDir(caps('speech'), s.dir)
    case 'name': return withDir('YOUR NAME', s.dir)
    case 'alarm': {
      const head = s.label === 'siren' ? 'SIREN' : 'ALARM'
      return [head, ...dirOnly(s.dir)]
    }
    default: return []
  }
}

export interface Hud {
  /** Pass to createStartUpPageContainer. */
  container: TextContainerProperty
  render(state: HudState): void
}

export function createHud(
  bridge: EvenAppBridge,
  onShow: (lines: string[], tier: Tier) => void = () => {},
): Hud {
  const container = new TextContainerProperty({
    xPosition: 0,
    yPosition: 0,
    width: WIDTH,
    height: HEIGHT,
    borderWidth: 0,
    borderColor: 5,
    paddingLength: PADDING,
    containerID: ID,
    containerName: NAME,
    content: ' ',
    isEventCapture: 1,
  })

  // What should be on screen now, and what was last written.
  let want = { content: ' ', level: 4 }
  let written = { content: ' ', level: 4 }
  let lastWriteAt = 0
  let writeTimer: number | null = null
  let writing = false

  let current: HudState = { state: 'idle' }
  let shownAt = 0
  let ttlTimer: number | null = null
  let speechHoldTimer: number | null = null
  let flashTimer: number | null = null
  let flashBright = true

  function flush() {
    writeTimer = null
    if (writing) return schedule()
    if (want.content === written.content && want.level === written.level) return
    const next = want
    writing = true
    lastWriteAt = Date.now()
    bridge
      .textContainerUpgrade(
        new TextContainerUpgrade({ containerID: ID, containerName: NAME, content: next.content, textColor: next.level }),
      )
      .then(() => (written = next))
      .catch(err => console.error('textContainerUpgrade failed:', err))
      .finally(() => {
        writing = false
        schedule()
      })
  }

  function schedule() {
    if (writeTimer !== null) return
    const wait = Math.max(0, lastWriteAt + MIN_WRITE_GAP_MS - Date.now())
    writeTimer = window.setTimeout(flush, wait)
  }

  // Draw `current` at its tier. Called on every new state and whenever the wearer changes a tier.
  function paint() {
    const lines = linesFor(current)
    const tier = tierFor(current)
    const urgent = lines.length > 0 && tier === 'urgent'
    if (!urgent && flashTimer !== null) {
      clearInterval(flashTimer)
      flashTimer = null
    }
    if (urgent && flashTimer === null) {
      flashBright = true
      flashTimer = window.setInterval(() => {
        flashBright = !flashBright
        want = { ...want, level: flashBright ? LEVEL.urgent : FLASH_DIM }
        schedule()
      }, FLASH_MS)
    }
    want = {
      content: lines.length ? centerBlock(lines) : ' ',
      level: urgent && !flashBright ? FLASH_DIM : LEVEL[tier],
    }
    onShow(lines, tier)
    schedule()
  }

  function show(s: HudState) {
    if (ttlTimer !== null) clearTimeout(ttlTimer)
    ttlTimer = null
    current = s
    shownAt = Date.now()
    paint()
    if (s.state !== 'idle' && s.ttl_ms && s.ttl_ms > 0) {
      ttlTimer = window.setTimeout(() => show({ state: 'idle' }), s.ttl_ms)
    }
  }

  onTiersChanged(paint)

  function render(s: HudState) {
    if (speechHoldTimer !== null) clearTimeout(speechHoldTimer)
    speechHoldTimer = null
    // Speech stays up at least 1 s; only a drop to idle waits, anything else replaces it now.
    const shownFor = Date.now() - shownAt
    if (current.state === 'speech' && s.state === 'idle' && shownFor < SPEECH_MIN_MS) {
      speechHoldTimer = window.setTimeout(() => show(s), SPEECH_MIN_MS - shownFor)
      return
    }
    show(s)
  }

  return { container, render }
}

/** ?demo=1: cycles idle, cue, speech, name, alarm every 4 s with no server. */
export const DEMO_STATES: HudState[] = [
  { state: 'idle' },
  { state: 'cue', label: 'doorbell', dir: 'right', ttl_ms: 0, level: 4 },
  { state: 'speech', label: 'speech', dir: 'left', ttl_ms: 0, level: 2 },
  { state: 'cue', label: 'knock', dir: 'front', ttl_ms: 0, level: 4 },
  { state: 'name', label: 'name', dir: 'left', ttl_ms: 0, level: 4 },
  { state: 'cue', label: 'snap', dir: 'behind', ttl_ms: 0, level: 4 },
  { state: 'alarm', label: 'siren', dir: 'behind', ttl_ms: 0, level: 4 },
]
