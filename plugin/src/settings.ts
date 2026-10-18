// Per-sound choice, set by the wearer on the glasses (long-press menu, menu.ts)
// or on the phone page (ui.ts), and kept in localStorage on the glasses phone.
//
//   off        never shown on the glasses
//   critical   S P A C E D  capitals in a bar frame, fast deep flashing   (phone: red)
//   medium     CAPITALS, slower shallow flashing                          (phone: orange)
//   normal     lowercase, dimmer, two blinks on arrival then steady       (phone: default)
//
// alarm and siren are locked on at critical so a fire alarm can never be muted
// or turned down.

import type { HudState } from './link'

export type Tier = 'critical' | 'medium' | 'normal'
export type Choice = Tier | 'off'
export type Label = NonNullable<HudState['label']>

export const LABELS: Label[] = ['alarm', 'siren', 'name', 'doorbell', 'knock', 'horn', 'dog', 'clap', 'snap', 'speech']
export const LOCKED: ReadonlySet<Label> = new Set(['alarm', 'siren'])

/** What each sound is called on the phone (this page, and the companion's alert screen). */
export const LABEL_NAMES: Record<Label, string> = {
  alarm: 'Smoke / fire alarm', siren: 'Siren', name: 'Your name', doorbell: 'Doorbell',
  knock: 'Knock', horn: 'Car horn', dog: 'Dog bark', clap: 'Clapping', snap: 'Finger snap',
  speech: 'Someone talking',
}

export const DEFAULTS: Record<Label, Tier> = {
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
const CHOICES: Choice[] = ['critical', 'medium', 'normal', 'off']
// Names saved before the rename to critical/medium/normal.
const OLD_NAMES: Record<string, Choice> = { urgent: 'critical', important: 'medium' }

function load(): Record<Label, Choice> {
  const choices: Record<Label, Choice> = { ...DEFAULTS }
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) ?? '{}') as Partial<Record<Label, string>>
    for (const l of LABELS) {
      const raw = saved[l]
      const c = (raw && (OLD_NAMES[raw] ?? raw)) as Choice | undefined
      if (c && CHOICES.includes(c) && !LOCKED.has(l)) choices[l] = c
    }
  } catch {
    // Storage blocked or corrupt: defaults are fine.
  }
  return choices
}

let choices = load()
const listeners = new Set<() => void>()

function save() {
  try {
    localStorage.setItem(KEY, JSON.stringify(choices))
  } catch {
    // Not persisted, but still applies for this session.
  }
  listeners.forEach(fn => fn())
}

export function choiceOf(label: Label): Choice {
  return choices[label]
}

/** Whether a state with this label may be shown. States without a label always may. */
export function isOn(label: HudState['label']): boolean {
  return !label || choices[label] !== 'off'
}

/** How a label is drawn. An off label has no tier of its own; it is never drawn. */
export function tierOf(label: HudState['label']): Tier {
  if (!label) return 'normal'
  const c = choices[label]
  return c === 'off' ? DEFAULTS[label] : c
}

export function setChoice(label: Label, choice: Choice) {
  if (LOCKED.has(label) || choices[label] === choice) return
  choices = { ...choices, [label]: choice }
  save()
}

/** Kept for the phone page: a tier is a choice that is not off. */
export const setTier = setChoice

/** A copy of every choice, for the glasses menu to edit as a draft. */
export function allChoices(): Record<Label, Choice> {
  return { ...choices }
}

/** Replace every choice at once (the glasses menu's DONE). Locked labels are kept as they are. */
export function setAll(next: Record<Label, Choice>) {
  const merged = { ...choices }
  for (const l of LABELS) if (!LOCKED.has(l) && CHOICES.includes(next[l])) merged[l] = next[l]
  choices = merged
  save()
}

export function onTiersChanged(fn: () => void): () => void {
  listeners.add(fn)
  return () => listeners.delete(fn)
}
