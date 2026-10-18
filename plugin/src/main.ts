import {
  waitForEvenAppBridge,
  CreateStartUpPageContainer,
  OsEventTypeList,
  AudioInputSource,
} from '@evenrealities/even_hub_sdk'
import { startLink, serverUrl, type Link } from './link'
import { createHud, DEMO_STATES } from './hud'
import { createAlertFeed } from './alerts'
import { createMenu } from './menu'
import type { HudState } from './link'
import { mountUi, setStatus, setHud, setMic } from './ui'

mountUi()

const bridge = await waitForEvenAppBridge()

// Whatever flashes on the glasses also rings the companion phone, through the server.
const alerts = createAlertFeed(frame => link?.send(frame))

const hud = createHud(bridge, (lines, tier, state) => {
  setHud(lines.length ? lines.join(' / ') : '(blank)', tier)
  alerts.update(state, tier)
})

const created = await bridge.createStartUpPageContainer(
  new CreateStartUpPageContainer({ containerTotalNum: 1, textObject: [hud.container] }),
)
if (created !== 0) {
  setStatus('error', `createStartUpPageContainer failed: ${created}`)
  console.error('Failed to create startup page')
}

// ── Sound menu (long-press) ────────────────────────────────────────

const menu = createMenu()

// Every HUD state goes through here. An alarm closes the menu without saving:
// the menu must never hide a fire alarm.
function onState(s: HudState) {
  if (menu.isOpen() && s.state === 'alarm') {
    menu.cancel()
    hud.hideMenu()
  }
  hud.render(s)
}

// ── Server link, or ?demo=1 ────────────────────────────────────────

const demo = new URLSearchParams(location.search).get('demo') === '1'
let link: Link | null = null
let demoTimer: number | null = null

if (demo) {
  let i = 0
  const step = () => onState(DEMO_STATES[i++ % DEMO_STATES.length])
  step()
  demoTimer = window.setInterval(step, 4000)
  setStatus('listening', 'Demo mode · no server')
} else {
  const url = serverUrl()
  link = startLink(url, onState, status => {
    if (status === 'open') {
      setStatus('listening', `Connected · ${url}`)
      alerts.resend() // anything sent while the socket was down was dropped
    }
    else if (status === 'connecting') setStatus('connecting', `Connecting · ${url}`)
    else setStatus('error', `Disconnected, retrying · ${url}`)
  })
}

// ── Mic, always on ─────────────────────────────────────────────────
// No tap-to-pause: Earshot has to hear the doorbell without the wearer touching anything.

const micOk = await bridge.audioControl(true, AudioInputSource.Glasses)
if (!micOk) setStatus('error', 'audioControl(true) returned false')

// Once-a-second mic stats on the phone page: proves frames keep coming with no touch.
let frames = 0
let sumSq = 0
let samples = 0
let lastDirection: number | null = null
let lastRole = 'unknown'
const statsTimer = window.setInterval(() => {
  const rms = samples ? Math.sqrt(sumSq / samples) : 0
  setMic(`${frames} frames/s · rms ${rms.toFixed(0)} · direction ${lastDirection} · speakerRole ${lastRole}`)
  frames = sumSq = samples = 0
}, 1000)

function countFrame(pcm: Uint8Array) {
  const view = new DataView(pcm.buffer, pcm.byteOffset, pcm.byteLength)
  for (let i = 0; i + 1 < pcm.byteLength; i += 2) {
    const s = view.getInt16(i, true)
    sumSq += s * s
  }
  samples += pcm.byteLength >> 1
  frames++
}

// ── Events and lifecycle ───────────────────────────────────────────

let cleanedUp = false
function cleanup() {
  if (cleanedUp) return
  cleanedUp = true
  bridge.audioControl(false)
  alerts.close() // before the socket closes, so the phone stops ringing
  link?.close()
  if (demoTimer !== null) clearInterval(demoTimer)
  clearInterval(statsTimer)
  unsubscribe()
}

// Reads the event type out of one envelope.
//
// CLICK_EVENT is 0, and protobuf omits zero-value fields on the wire, so a
// single tap arrives as an envelope whose `eventType` is `undefined`. The
// default has to be resolved INSIDE the envelope check, or every audio frame
// (which carries no `sysEvent`) would read as a tap.
function eventTypeOf(envelope?: { eventType?: OsEventTypeList }): OsEventTypeList | null {
  if (!envelope) return null
  return envelope.eventType ?? OsEventTypeList.CLICK_EVENT
}

// Touchpad, menu open (menu.ts): swipe moves, tap changes, long-press saves,
// double-tap closes without saving. Menu closed: long-press opens it and
// double-tap → `shutDownPageContainer(1)` exits; SYSTEM_EXIT_EVENT fires on confirm.
const unsubscribe = bridge.onEvenHubEvent(event => {
  const audio = event.audioEvent
  if (audio?.audioPcm) {
    countFrame(audio.audioPcm)
    lastDirection = audio.direction
    lastRole = audio.speakerRole
    link?.sendAudio(audio)
  }

  const sysType = eventTypeOf(event.sysEvent)
  const textType = eventTypeOf(event.textEvent)
  const is = (t: OsEventTypeList) => sysType === t || textType === t

  if (is(OsEventTypeList.SYSTEM_EXIT_EVENT) || is(OsEventTypeList.ABNORMAL_EXIT_EVENT)) {
    cleanup()
    return
  }

  if (menu.isOpen()) {
    if (is(OsEventTypeList.DOUBLE_CLICK_EVENT)) {
      menu.cancel()
      hud.hideMenu()
      return
    }
    if (is(OsEventTypeList.LONG_PRESS_EVENT)) {
      menu.save()
      hud.hideMenu()
      return
    }
    if (is(OsEventTypeList.SCROLL_TOP_EVENT)) menu.up()
    else if (is(OsEventTypeList.SCROLL_BOTTOM_EVENT)) menu.down()
    else if (is(OsEventTypeList.CLICK_EVENT) && menu.tap()) {
      hud.hideMenu() // DONE
      return
    }
    hud.showMenu(menu.lines())
    return
  }

  if (is(OsEventTypeList.DOUBLE_CLICK_EVENT)) {
    bridge.shutDownPageContainer(1)
    return
  }
  if (is(OsEventTypeList.LONG_PRESS_EVENT)) {
    menu.open()
    hud.showMenu(menu.lines())
  }
})

window.addEventListener('beforeunload', cleanup)
