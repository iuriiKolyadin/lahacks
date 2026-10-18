import { LABELS, LABEL_NAMES, LOCKED, setChoice, choiceOf, onTiersChanged, type Choice, type Tier } from './settings'

type Status = 'connecting' | 'listening' | 'paused' | 'error'

const CHOICE_NAMES: Record<Choice, string> = { critical: 'Critical', medium: 'Medium', normal: 'Normal', off: 'Off' }

let statusEl: HTMLDivElement
let hudEl: HTMLDivElement
let micEl: HTMLDivElement

export function mountUi() {
  const app = document.querySelector<HTMLDivElement>('#app')!
  app.innerHTML = `
    <main class="panel">
      <header>
        <h1>Earshot</h1>
        <div id="status" class="status status-connecting">Connecting…</div>
      </header>
      <section class="transcript" aria-live="polite">
        <div class="label">HUD</div>
        <div id="hud">idle</div>
        <div class="label">Mic</div>
        <div id="mic" class="interim">waiting for audio…</div>
      </section>
      <section class="tiers">
        <div class="label">Alert levels</div>
        <p class="hint">Off sounds never show. Critical shows spaced capitals in a frame and flashes fast. Medium shows capitals and flashes slowly. Normal is dimmer and blinks twice. Critical and Medium also ring the Earshot Companion phone like a call. On the glasses: long-press for the same menu.</p>
        <div id="tier-rows"></div>
      </section>
      <footer>Double-tap the glasses temple to exit.</footer>
    </main>
  `
  statusEl = app.querySelector<HTMLDivElement>('#status')!
  hudEl = app.querySelector<HTMLDivElement>('#hud')!
  micEl = app.querySelector<HTMLDivElement>('#mic')!
  mountTiers(app.querySelector<HTMLDivElement>('#tier-rows')!)
  injectStyles()
}

// One row per sound with a Critical / Medium / Normal / Off picker. alarm and siren are locked.
function mountTiers(root: HTMLDivElement) {
  const draw = () => {
    root.innerHTML = LABELS.map(label => {
      const locked = LOCKED.has(label)
      const buttons = (Object.keys(CHOICE_NAMES) as Choice[])
        .map(t => {
          const on = choiceOf(label) === t
          return `<button class="tier-btn tier-${t}${on ? ' on' : ''}" data-label="${label}" data-tier="${t}"
            ${locked ? 'disabled' : ''} aria-pressed="${on}">${CHOICE_NAMES[t]}</button>`
        })
        .join('')
      return `<div class="tier-row"><span class="tier-name tier-text-${choiceOf(label)}">${LABEL_NAMES[label]}${
        locked ? ' <small>(always critical)</small>' : ''
      }</span><span class="tier-picker">${buttons}</span></div>`
    }).join('')
  }
  root.addEventListener('click', e => {
    const btn = (e.target as HTMLElement).closest<HTMLButtonElement>('button[data-label]')
    if (!btn || btn.disabled) return
    setChoice(btn.dataset.label as (typeof LABELS)[number], btn.dataset.tier as Choice)
  })
  onTiersChanged(draw)
  draw()
}

export function setStatus(kind: Status, text: string) {
  if (!statusEl) return
  statusEl.className = `status status-${kind}`
  statusEl.textContent = text
}

/** Mirror of what the glasses show, coloured by tier (the glasses themselves are green only). */
export function setHud(text: string, tier: Tier = 'normal') {
  if (!hudEl) return
  hudEl.textContent = text
  hudEl.className = `tier-text-${tier}`
}

/** Once-a-second mic stats line. */
export function setMic(text: string) {
  if (micEl) micEl.textContent = text
}

function injectStyles() {
  // ER brand dark-theme surfaces: #232323 / #2E2E2E / #3E3E3E.
  // ER OS green (#3CFA44) + signal red (#FF453A) for state chips.
  const css = `
    :root { color-scheme: dark; }
    html, body { margin: 0; min-height: 100%; background: #232323; color: #E5E5E5;
      font: 16px/1.4 -apple-system, BlinkMacSystemFont, 'Helvetica Neue', system-ui, sans-serif;
      touch-action: manipulation; -webkit-text-size-adjust: 100%;
      overscroll-behavior: none; }
    #app { display: flex; }
    .panel { display: flex; flex-direction: column; gap: 16px;
      width: 100%; max-width: 640px; margin: 0 auto; padding: 24px; box-sizing: border-box; }
    header { display: flex; align-items: center; justify-content: space-between; }
    h1 { font-size: 18px; font-weight: 600; margin: 0; letter-spacing: 0.02em; }
    .status { font-size: 12px; padding: 4px 10px; border-radius: 999px;
      border: 1px solid transparent; letter-spacing: 0.04em; text-transform: uppercase; }
    .status-connecting { color: #A7A7A7; border-color: #3E3E3E; }
    .status-listening  { color: #3CFA44; border-color: #3CFA44; background: rgba(60,250,68,0.08); }
    .status-paused     { color: #E5E5E5; border-color: #7B7B7B; background: rgba(229,229,229,0.06); }
    .status-error      { color: #FF453A; border-color: #FF453A; background: rgba(255,69,58,0.08); }
    .transcript { overflow: auto; background: #2E2E2E; border: 1px solid #3E3E3E;
      color: #E5E5E5;
      border-radius: 12px; padding: 20px; font-size: 18px; line-height: 1.5;
      min-height: 120px; white-space: pre-wrap; word-break: break-word; }
    .interim { color: #919191; font-size: 14px; }
    .label { font-size: 11px; color: #7B7B7B; text-transform: uppercase; letter-spacing: 0.08em; margin-top: 8px; }
    footer { font-size: 12px; color: #7B7B7B; text-align: center; }
    .tier-text-critical { color: #FF453A; font-weight: 600; }
    .tier-text-medium { color: #FF9F0A; font-weight: 600; }
    .tier-text-normal { color: #E5E5E5; }
    .tier-text-off { color: #7B7B7B; text-decoration: line-through; }
    .tiers { background: #2E2E2E; border: 1px solid #3E3E3E; border-radius: 12px; padding: 16px 20px; }
    .hint { font-size: 12px; color: #919191; margin: 4px 0 12px; }
    .tier-row { display: flex; align-items: center; justify-content: space-between; gap: 8px;
      padding: 8px 0; border-top: 1px solid #3E3E3E; flex-wrap: wrap; }
    .tier-name { font-size: 15px; }
    .tier-name small { color: #7B7B7B; font-weight: 400; }
    .tier-picker { display: flex; gap: 4px; }
    .tier-btn { font: inherit; font-size: 12px; padding: 6px 10px; border-radius: 999px;
      border: 1px solid #3E3E3E; background: transparent; color: #A7A7A7; }
    .tier-btn:disabled { opacity: 0.4; }
    .tier-btn.on:disabled { opacity: 1; }
    .tier-critical.on { color: #FF453A; border-color: #FF453A; background: rgba(255,69,58,0.12); }
    .tier-medium.on { color: #FF9F0A; border-color: #FF9F0A; background: rgba(255,159,10,0.12); }
    .tier-normal.on { color: #E5E5E5; border-color: #7B7B7B; background: rgba(229,229,229,0.08); }
    .tier-off.on { color: #A7A7A7; border-color: #5B5B5B; background: rgba(120,120,120,0.12); }
  `
  const style = document.createElement('style')
  style.textContent = css
  document.head.appendChild(style)
}
