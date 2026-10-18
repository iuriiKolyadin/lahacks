// Per-sound alert tier, chosen by the wearer on the phone page and kept in localStorage.
//
//   urgent     brightest, flashing, UPPERCASE      (phone: red)
//   important  brightest, steady, UPPERCASE        (phone: orange)
//   normal     dimmer, steady, lowercase           (phone: default)
//
// alarm and siren are locked to urgent so a fire alarm can never be turned down.

import type { HudState } from './link'

export type Tier = 'urgent' | 'important' | 'normal'
export type Label = NonNullable<HudState['label']>

export const LABELS: Label[] = ['alarm', 'siren', 'name', 'doorbell', 'knock', 'horn', 'dog', 'clap', 'snap', 'speech']
export const LOCKED: ReadonlySet<Label> = new Set(['alarm', 'siren'])

const DEFAULTS: Record<Label, Tier> = {
  alarm: 'urgent',
  siren: 'urgent',
  name: 'important',
  doorbell: 'important',
  knock: 'important',
  horn: 'important',
  dog: 'normal',
  clap: 'normal',
  snap: 'normal',
  speech: 'normal',
}

const KEY = 'earshot.tiers.v1'
const TIERS: Tier[] = ['urgent', 'important', 'normal']

function load(): Record<Label, Tier> {
  const tiers = { ...DEFAULTS }
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) ?? '{}') as Partial<Record<Label, Tier>>
    for (const l of LABELS) {
      const t = saved[l]
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
