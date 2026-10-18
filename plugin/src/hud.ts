// Draws a HudState (PRD.md section 5) on the glasses.
//
// One full-screen text container, updated only with textContainerUpgrade,
// brightness via textColor, at least 150 ms between writes (only the latest
// pending state is written; older ones are dropped, never queued).
//
// The G2 is monochrome green with one fixed font (no size control), so the
// wearer's alert tiers (settings.ts) are drawn with spacing, a bar frame,
// case, brightness and flashing. The server's `level` field is ignored; the
// tier decides.
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
import { tierOf, isOn, onTiersChanged, type Tier } from './settings'

const ID = 1
const NAME = 'hud'
const WIDTH = 576
const HEIGHT = 288
const PADDING = 4
const MIN_WRITE_GAP_MS = 150
const SPEECH_MIN_MS = 1000
const LEVEL: Record<Tier, number> = { critical: 4, medium: 4, normal: 2 }
// How each tier flashes: toggle between LEVEL and `dim` every `ms`, `times`
// toggles in all (Infinity = for as long as it is shown), then hold LEVEL.
const FLASH: Record<Tier, { ms: number; dim: number; times: number }> = {
  critical: { ms: 300, dim: 1, times: Infinity }, // fast and deep
  medium: { ms: 700, dim: 2, times: Infinity }, // slower and shallower
  normal: { ms: 500, dim: 1, times: 4 }, // two blinks on arrival, then steady
}

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
// center is ahead OR behind (the G2's two mics cannot tell which), drawn as
// both. near has none. ASCII only: the firmware font's other glyphs are unverified.
const ARROW_LEFT = '<-----'
const ARROW_RIGHT = '----->'
const ARROW_UP = ['^', '|', '|']
const ARROW_DOWN = ['|', '|', 'v']

// Display text for a label; the server's ids are short.
const SHOW: Partial<Record<NonNullable<HudState['label']>, string>> = { clap: 'clapping', snap: 'snap', dog: 'dog bark' }

// The label as its tier draws it: critical is S P A C E D capitals between two
// bars (the closest thing to a bigger font), medium is capitals, normal is as is.
// Alarm and siren are plain capitals: the word itself is the emphasis, and the
// arrows must touch it.
function styled(text: string, tier: Tier, plain = false): string[] {
  if (tier === 'normal') return [text]
  const caps = text.toUpperCase()
  if (tier === 'medium' || plain) return [caps]
  const spaced = caps.split('').join(' ')
  const bar = '='.repeat(Math.max(3, Math.ceil(textPx(spaced) / textPx('='))))
  return [bar, spaced, bar]
}

// Side arrows go on the label's own line. Vertical arrows sit directly above
// and below the label, so a framed block drops its bars for them (the bars
// would come between arrow and word, and 3 + 3 + 3 lines would not fit the 8
// rows of the display).
function withDir(block: string[], dir: HudState['dir']): string[] {
  const label = block[Math.floor(block.length / 2)]
  switch (dir) {
    case 'left': return block.map(l => (l === label ? `${ARROW_LEFT}  ${l}` : l))
    case 'right': return block.map(l => (l === label ? `${l}  ${ARROW_RIGHT}` : l))
    case 'front': return [...ARROW_UP, label]
    case 'behind': return [label, ...ARROW_DOWN]
    case 'center': return [...ARROW_UP, label, ...ARROW_DOWN]
    default: return block
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
  const tier = tierFor(s)
  switch (s.state) {
    case 'cue': return withDir(styled((s.label && SHOW[s.label]) ?? s.label ?? '', tier), s.dir)
    case 'speech': return withDir(styled('speech', tier), s.dir)
    case 'name': return withDir(styled('your name', tier === 'normal' ? 'medium' : tier), s.dir)
    case 'alarm': return withDir(styled(s.label === 'siren' ? 'siren' : 'alarm', tier, true), s.dir)
    default: return []
  }
}

export interface Hud {
  /** Pass to createStartUpPageContainer. */
  container: TextContainerProperty
  render(state: HudState): void
  /** Draw the sound menu (menu.ts) instead of the HUD. Call again on every change. */
  showMenu(lines: string[]): void
  /** Back to the HUD, redrawn as it is now. */
  hideMenu(): void
}

export function createHud(
  bridge: EvenAppBridge,
  onShow: (lines: string[], tier: Tier, state: HudState) => void = () => {},
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
  let menuOpen = false

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

  // Draw `current` at its tier and (re)start that tier's flashing. Called on
  // every new state and whenever the wearer changes a tier.
  function paint() {
    if (flashTimer !== null) clearInterval(flashTimer)
    flashTimer = null
    if (menuOpen) return // the menu owns the display; current is drawn when it closes
    const lines = linesFor(current)
    const tier = tierFor(current)
    want = { content: lines.length ? centerBlock(lines) : ' ', level: LEVEL[tier] }
    if (lines.length) {
      const { ms, dim, times } = FLASH[tier]
      let toggles = 0
      flashTimer = window.setInterval(() => {
        toggles++
        const bright = toggles % 2 === 0
        want = { ...want, level: bright ? LEVEL[tier] : dim }
        schedule()
        if (toggles >= times && bright && flashTimer !== null) {
          clearInterval(flashTimer) // finished its blinks on a bright frame
          flashTimer = null
        }
      }, ms)
    }
    onShow(lines, tier, current)
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
    if (!isOn(s.label)) s = { state: 'idle' } // the wearer switched this sound off
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

  function showMenu(lines: string[]) {
    menuOpen = true
    if (flashTimer !== null) clearInterval(flashTimer)
    flashTimer = null
    want = { content: lines.join('\n'), level: LEVEL.critical }
    schedule()
  }

  function hideMenu() {
    if (!menuOpen) return
    menuOpen = false
    paint()
  }

  return { container, render, showMenu, hideMenu }
}

/** ?demo=1: cycles idle, cue, speech, name, alarm every 4 s with no server. */
export const DEMO_STATES: HudState[] = [
  { state: 'idle' },
  { state: 'cue', label: 'doorbell', dir: 'right', ttl_ms: 0, level: 4 },
  { state: 'speech', label: 'speech', dir: 'left', ttl_ms: 0, level: 2 },
  { state: 'cue', label: 'knock', dir: 'front', ttl_ms: 0, level: 4 },
  { state: 'name', label: 'name', dir: 'left', ttl_ms: 0, level: 4 },
  { state: 'cue', label: 'snap', dir: 'center', ttl_ms: 0, level: 4 },
  { state: 'alarm', label: 'siren', dir: 'behind', ttl_ms: 0, level: 4 },
]
