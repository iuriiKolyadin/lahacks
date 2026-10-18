// The sound menu on the glasses: which sounds to show, and at what level.
//
//   tap (HUD)           open the menu (long-press opens Even AI instead)
//   swipe up / down     move the cursor
//   tap                 on a sound: off -> normal -> medium -> critical -> off
//                       on ALL SOUNDS: everything on, or everything off if all were on
//                       on DONE: save and close
//   long-press (menu)   save and close, if the glasses pass it through
//   double-tap (menu)   close without saving
//
// Changes are a draft until saved, so a wrong tap can be thrown away. Alarm
// and siren are locked on at critical (settings.ts). Drawn as plain
// left-aligned text in the HUD's one text container (hud.ts showMenu).

import { LABELS, LOCKED, DEFAULTS, allChoices, setAll, type Choice, type Label } from './settings'

const NAMES: Record<Label, string> = {
  alarm: 'Fire alarm', siren: 'Siren', name: 'Your name', doorbell: 'Doorbell', knock: 'Knock',
  horn: 'Car horn', dog: 'Dog bark', clap: 'Clapping', snap: 'Finger snap', speech: 'Talking',
}
const NEXT: Record<Choice, Choice> = { off: 'normal', normal: 'medium', medium: 'critical', critical: 'off' }
const SHOWN: Record<Choice, string> = { off: 'off', normal: 'normal', medium: 'MEDIUM', critical: 'CRITICAL' }

type Row = 'all' | Label | 'done'
const ROWS: Row[] = ['all', ...LABELS, 'done']
// The display fits 8 lines (hud.ts LINE_PX 32 on 288 px): one title, seven rows.
const VISIBLE = 7

export interface Menu {
  isOpen(): boolean
  open(): void
  up(): void
  down(): void
  /** Returns true when the tap saved and closed the menu (DONE). */
  tap(): boolean
  save(): void
  cancel(): void
  lines(): string[]
}

export function createMenu(): Menu {
  let opened = false
  let cursor = 0
  let draft: Record<Label, Choice> = allChoices()

  const editable = () => LABELS.filter(l => !LOCKED.has(l))
  const allOn = () => editable().every(l => draft[l] !== 'off')

  function rowText(row: Row): string {
    if (row === 'all') return `All sounds: ${allOn() ? 'ON' : 'off'}`
    if (row === 'done') return '[ DONE ]'
    return `${NAMES[row]}: ${SHOWN[draft[row]]}${LOCKED.has(row) ? ' (always)' : ''}`
  }

  return {
    isOpen: () => opened,
    open() {
      draft = allChoices()
      cursor = 0
      opened = true
    },
    up() {
      cursor = Math.max(0, cursor - 1)
    },
    down() {
      cursor = Math.min(ROWS.length - 1, cursor + 1)
    },
    tap() {
      const row = ROWS[cursor]
      if (row === 'done') {
        this.save()
        return true
      }
      if (row === 'all') {
        const on = !allOn()
        for (const l of editable()) {
          if (!on) draft[l] = 'off'
          else if (draft[l] === 'off') draft[l] = DEFAULTS[l]
        }
      } else if (!LOCKED.has(row)) {
        draft[row] = NEXT[draft[row]]
      }
      return false
    },
    save() {
      setAll(draft)
      opened = false
    },
    cancel() {
      opened = false
    },
    lines() {
      const start = Math.max(0, Math.min(cursor - Math.floor(VISIBLE / 2), ROWS.length - VISIBLE))
      const rows = ROWS.slice(start, start + VISIBLE).map((row, i) =>
        (start + i === cursor ? '> ' : '    ') + rowText(row),
      )
      return ['SOUNDS   tap = change, hold = save', ...rows]
    },
  }
}
