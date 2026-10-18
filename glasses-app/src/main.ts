// Milestone 0: "hello" on the glasses, plus three hardware checks shown on the
// lenses and the phone page:
//   1. the YAMNet model loads and runs inside the Even app's WebView (WASM test)
//   2. the glasses mic delivers PCM, and at what rate
//   3. whether the `direction` tag carries data on this firmware
import {
  AudioInputSource,
  CreateStartUpPageContainer,
  OsEventTypeList,
  StartUpPageCreateResult,
  TextContainerProperty,
  TextContainerUpgrade,
  type EvenAppBridge,
} from '@evenrealities/even_hub_sdk'
import { connectBridge } from './bridge'
import { createMediaPipeClassifier } from './classify/mediapipe'
import { log } from './log'

const CONTAINER = { containerID: 1, containerName: 'hud' }

const hudEl = document.getElementById('hud')!
const statsEl = document.getElementById('stats')!

let modelLine = 'model: loading...'
let micLine = 'mic: waiting...'

let bridge: EvenAppBridge | null = null

async function createPage(b: EvenAppBridge) {
  const text = new TextContainerProperty({
    xPosition: 0,
    yPosition: 0,
    width: 576,
    height: 288,
    borderWidth: 0,
    paddingLength: 8,
    ...CONTAINER,
    content: 'hello',
    isEventCapture: 1,
  })
  const res = await b.createStartUpPageContainer(
    new CreateStartUpPageContainer({ containerTotalNum: 1, textObject: [text] }),
  )
  log('page', res === StartUpPageCreateResult.success ? 'created' : `create FAILED: ${res}`)

  b.onEvenHubEvent(event => {
    const pcm = event.audioEvent?.audioPcm
    if (pcm) {
      onPcm(pcm, event.audioEvent!.direction, event.audioEvent!.speakerRole)
      return
    }
    const sysType = eventTypeOf(event.sysEvent)
    const textType = eventTypeOf(event.textEvent)
    if (sysType === OsEventTypeList.DOUBLE_CLICK_EVENT || textType === OsEventTypeList.DOUBLE_CLICK_EVENT) {
      log('input', 'double tap -> system exit dialog')
      void b.shutDownPageContainer(1)
      return
    }
    if (sysType === OsEventTypeList.CLICK_EVENT || textType === OsEventTypeList.CLICK_EVENT) {
      log('input', 'tap')
      return
    }
    if (sysType === OsEventTypeList.FOREGROUND_ENTER_EVENT) {
      log('life', 'foreground enter -> restarting mic')
      void b.audioControl(true, AudioInputSource.Glasses)
    } else if (sysType === OsEventTypeList.SYSTEM_EXIT_EVENT || sysType === OsEventTypeList.ABNORMAL_EXIT_EVENT) {
      log('life', 'exit -> stopping mic')
      void b.audioControl(false)
    } else if (sysType !== null) {
      log('event', `sys ${sysType}`)
    }
  })
}

// CLICK_EVENT is 0 and protobuf drops zero fields, so a tap arrives with
// `eventType` undefined. Resolve the default only when the envelope exists.
function eventTypeOf(envelope?: { eventType?: OsEventTypeList }): OsEventTypeList | null {
  if (!envelope) return null
  return envelope.eventType ?? OsEventTypeList.CLICK_EVENT
}

async function selfTestModel() {
  try {
    const t = performance.now()
    const classifier = await createMediaPipeClassifier()
    const loadMs = Math.round(performance.now() - t)
    // One 0.975 s YAMNet patch of a 1 kHz tone: expect "Beep, bleep" or "Sine wave".
    const sr = 16000
    const tone = new Float32Array(15600).map((_, i) => 0.5 * Math.sin((2 * Math.PI * 1000 * i) / sr))
    const t2 = performance.now()
    const top = classifier.classify(tone, sr)
    const runMs = Math.round(performance.now() - t2)
    log('model', `self-test top: ${top.map(s => `${s.label} ${s.score.toFixed(2)}`).join(', ')} (${runMs} ms)`)
    modelLine = `model OK: load ${loadMs} ms, run ${runMs} ms\n  heard "${top[0]?.label}" ${top[0]?.score.toFixed(2)}`
  } catch (err) {
    log('model', `FAILED: ${(err as Error)?.message ?? err}`)
    modelLine = `model FAILED: ${String((err as Error)?.message ?? err).slice(0, 60)}`
  }
  render()
}

// Mic statistics, reported once a second.
let bytes = 0
let frames = 0
let dirCount = 0
let dirMin = Infinity
let dirMax = -Infinity
let dirLast: number | null = null
const roles: Record<string, number> = {}

function startMic(b: EvenAppBridge) {
  void b.audioControl(true, AudioInputSource.Glasses).then(ok => log('mic', `audioControl(true, glasses) -> ${ok}`))
  setInterval(() => {
    const rate = bytes / 2
    const dir = dirCount ? `last ${dirLast}, range ${dirMin}..${dirMax}` : 'always null'
    micLine = frames ? `mic: ${rate} samples/s, ${frames} frames/s\n  direction: ${dir}` : 'mic: no audio yet'
    log('mic', `${rate} samples/s in ${frames} frames; direction ${dir}; roles ${JSON.stringify(roles)}`)
    bytes = frames = dirCount = 0
    dirMin = Infinity
    dirMax = -Infinity
    for (const k of Object.keys(roles)) delete roles[k]
    render()
  }, 1000)
}

function onPcm(pcm: Uint8Array, direction: number | null, role: string) {
  bytes += pcm.length
  frames++
  roles[role] = (roles[role] ?? 0) + 1
  if (direction !== null && direction !== undefined) {
    dirCount++
    dirLast = direction
    dirMin = Math.min(dirMin, direction)
    dirMax = Math.max(dirMax, direction)
  }
}

let lastWritten = ''
function render() {
  const content = `hello\n\n${modelLine}\n${micLine}`
  hudEl.textContent = content
  statsEl.textContent = bridge ? 'Running inside the Even app.' : 'Browser mode: no Even app, so no glasses or mic.'
  if (!bridge || content === lastWritten) return
  lastWritten = content
  void bridge.textContainerUpgrade(new TextContainerUpgrade({ ...CONTAINER, content }))
}

// Startup. Kept last so every module-level `let` above is initialised first.
log('boot', navigator.userAgent)
log('boot', `WebAssembly: ${typeof WebAssembly === 'object' ? 'yes' : 'NO'}`)
bridge = await connectBridge()
if (bridge) await createPage(bridge)
render()
void selfTestModel()
if (bridge) startMic(bridge)
