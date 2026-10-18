import {
  waitForEvenAppBridge,
  CreateStartUpPageContainer,
  OsEventTypeList,
  AudioInputSource,
} from '@evenrealities/even_hub_sdk'
import { startLink, serverUrl, type Link } from './link'
import { createHud, DEMO_STATES } from './hud'
import { mountUi, setStatus, setHud, setMic } from './ui'

mountUi()

const bridge = await waitForEvenAppBridge()

const hud = createHud(bridge, (lines, tier) => setHud(lines.length ? lines.join(' / ') : '(blank)', tier))

const created = await bridge.createStartUpPageContainer(
  new CreateStartUpPageContainer({ containerTotalNum: 1, textObject: [hud.container] }),
)
if (created !== 0) {
  setStatus('error', `createStartUpPageContainer failed: ${created}`)
  console.error('Failed to create startup page')
}

// ── Server link, or ?demo=1 ────────────────────────────────────────

const demo = new URLSearchParams(location.search).get('demo') === '1'
let link: Link | null = null
let demoTimer: number | null = null

if (demo) {
  let i = 0
  const step = () => hud.render(DEMO_STATES[i++ % DEMO_STATES.length])
  step()
  demoTimer = window.setInterval(step, 4000)
  setStatus('listening', 'Demo mode · no server')
} else {
  const url = serverUrl()
  link = startLink(url, hud.render, status => {
    if (status === 'open') setStatus('listening', `Connected · ${url}`)
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

// Double-tap → `shutDownPageContainer(1)` is checked first and on every
// envelope, so the wearer can always exit. SYSTEM_EXIT_EVENT fires on confirm.
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

  if (sysType === OsEventTypeList.DOUBLE_CLICK_EVENT || textType === OsEventTypeList.DOUBLE_CLICK_EVENT) {
    bridge.shutDownPageContainer(1)
    return
  }

  if (sysType === OsEventTypeList.SYSTEM_EXIT_EVENT || sysType === OsEventTypeList.ABNORMAL_EXIT_EVENT) {
    cleanup()
  }
})

window.addEventListener('beforeunload', cleanup)
