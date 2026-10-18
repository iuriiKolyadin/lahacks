// Tells the Earshot Companion phone when the glasses are flashing an alert, so
// the phone can ring like an incoming call and offer the wearer's spoken replies.
//
// Only tiers that keep flashing ring the phone: critical and medium. Normal
// blinks twice and goes steady, so it stays on the glasses. The wearer already
// picks each sound's tier on this page; turning a sound down to Normal also
// stops it ringing the phone.
//
// Frames go up the server socket. server/main.py relays them unchanged to
// /ws/pendant, where the companion listens (docs/BRIDGE.md, "alert"):
//
//   {"v":1,"type":"alert","id":"a1760745600123-1","active":true,"state":"cue",
//    "label":"doorbell","text":"Doorbell","dir":"right","tier":"medium","ts":...}
//   {"v":1,"type":"alert","id":"a1760745600123-1","active":false,"ts":...}
//
// One id per sound: the same sound changing direction keeps its id, a
// different sound gets a new one (the phone replaces the old alert). While
// active, the frame is resent every 5 s, so a phone that connects late still
// rings, and one that loses the link times the alert out instead of ringing forever.

import type { HudState } from './link'
import { LABEL_NAMES, type Label, type Tier } from './settings'

const RINGS: ReadonlySet<Tier> = new Set(['critical', 'medium'])
const REFRESH_MS = 5000

type AlertFrame = {
  v: 1
  type: 'alert'
  id: string
  active: true
  state: HudState['state']
  label: string
  text: string
  dir: NonNullable<HudState['dir']>
  tier: Tier
}

export interface AlertFeed {
  /** Call with every state the HUD draws, at the tier it draws it. */
  update(state: HudState, tier: Tier): void
  /** Send the active alert again now, e.g. after the socket reconnects. */
  resend(): void
  /** Clear any active alert on the phone and stop refreshing. */
  close(): void
}

// The sound behind a state, matching how hud.ts picks its tier.
function labelOf(s: HudState): string {
  if (s.state === 'alarm') return s.label === 'siren' ? 'siren' : 'alarm'
  if (s.state === 'name' || s.state === 'speech') return s.state
  return s.label ?? 'sound'
}

function textOf(label: string): string {
  if (label === 'name') return 'Someone said your name'
  return LABEL_NAMES[label as Label] ?? label
}

export function createAlertFeed(send: (frame: object) => void): AlertFeed {
  let active: AlertFrame | null = null
  let refresh: number | null = null
  let count = 0 // with the time, unique across reloads and within one millisecond

  const emit = () => {
    if (active) send({ ...active, ts: Date.now() })
  }

  function clear() {
    if (refresh !== null) clearInterval(refresh)
    refresh = null
    if (!active) return
    send({ v: 1, type: 'alert', id: active.id, active: false, ts: Date.now() })
    active = null
  }

  return {
    update(state, tier) {
      if (state.state === 'idle' || !RINGS.has(tier)) return clear()
      const label = labelOf(state)
      const sameSound = active?.state === state.state && active.label === label
      const next: AlertFrame = {
        v: 1,
        type: 'alert',
        id: sameSound && active ? active.id : `a${Date.now()}-${++count}`,
        active: true,
        state: state.state,
        label,
        text: textOf(label),
        dir: state.dir ?? 'near',
        tier,
      }
      // A repaint of what the phone already has (same frame from the server, or a tier
      // change that still rings at the same tier): nothing to tell it.
      if (active && JSON.stringify(next) === JSON.stringify(active)) return
      active = next
      emit()
      if (refresh === null) refresh = window.setInterval(emit, REFRESH_MS)
    },
    resend: emit,
    close: clear,
  }
}
