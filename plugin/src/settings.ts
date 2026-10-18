// Per-sound alert tier, chosen by the wearer on the phone page and kept in localStorage.
//
//   critical   S P A C E D  capitals in a bar frame, fast deep flashing   (phone: red)
//   medium     CAPITALS, slower shallow flashing                          (phone: orange)
//   normal     lowercase, dimmer, two blinks on arrival then steady       (phone: default)
//
// alarm and siren are locked to critical so a fire alarm can never be turned down.

import type { HudState } from './link'

export type Tier = 'critical' | 'medium' | 'normal'
export type Label = NonNullable<HudState['label']>

export const LABELS: Label[] = ['alarm', 'siren', 'name', 'doorbell', 'knock', 'horn', 'dog', 'clap', 'snap', 'speech']
export const LOCKED: ReadonlySet<Label> = new Set(['alarm', 'siren'])

const DEFAULTS: Record<Label, Tier> = {
  alarm: 'critical',
  siren: 'critical',
  name: 'medium',
  doorbell: 'medium',
  knock: 'medium',
  horn: 'medium',
  dog: 'normal',
  clap: 'normal',
  snap: 'normal',
  speech: 'normal',
}

const KEY = 'earshot.tiers.v1'
const TIERS: Tier[] = ['critical', 'medium', 'normal']
// Names saved before the rename to critical/medium/normal.
const OLD_NAMES: Record<string, Tier> = { urgent: 'critical', important: 'medium' }

function load(): Record<Label, Tier> {
  const tiers = { ...DEFAULTS }
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) ?? '{}') as Partial<Record<Label, string>>
    for (const l of LABELS) {
      const raw = saved[l]
      const t = (raw && (OLD_NAMES[raw] ?? raw)) as Tier | undefined
      if (t && TIERS.includes(t) && !LOCKED.has(l)) tiers[l] = t
    }
  } catch {
    // Storage blocked or corrupt: defaults are fine.
  }
  return tiers
}

let tiers = load()
const listeners = new Set<() => void>()

export function tierOf(label: HudState['label']): Tier {
  return label ? tiers[label] : 'normal'
}

export function setTier(label: Label, tier: Tier) {
  if (LOCKED.has(label) || tiers[label] === tier) return
  tiers = { ...tiers, [label]: tier }
  try {
    localStorage.setItem(KEY, JSON.stringify(tiers))
  } catch {
    // Not persisted, but still applies for this session.
  }
  listeners.forEach(fn => fn())
}

export function onTiersChanged(fn: () => void): () => void {
  listeners.add(fn)
  return () => listeners.delete(fn)
}
