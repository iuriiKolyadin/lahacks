import { LABELS, LABEL_NAMES, LOCKED, setTier, tierOf, onTiersChanged, type Tier } from './settings'

type Status = 'connecting' | 'listening' | 'paused' | 'error'

const TIER_NAMES: Record<Tier, string> = { critical: 'Critical', medium: 'Medium', normal: 'Normal' }

let statusEl: HTMLDivElement
let hudEl: HTMLDivElement
let micEl: HTMLDivElement

export function mountUi() {
  const app = document.querySelector<HTMLDivElement>('#app')!
  app.innerHTML = `
    <main class="panel">
      <header>
        <h1>Cue</h1>
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
        <p class="hint">Critical shows spaced capitals in a frame and flashes fast. Medium shows capitals and flashes slowly. Normal is dimmer and blinks twice. Critical and Medium also ring the Cue Companion phone like a call.</p>
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

// One row per sound with a Critical / Medium / Normal picker. alarm and siren are locked.
function mountTiers(root: HTMLDivElement) {
  const draw = () => {
    root.innerHTML = LABELS.map(label => {
      const locked = LOCKED.has(label)
      const buttons = (Object.keys(TIER_NAMES) as Tier[])
        .map(t => {
          const on = tierOf(label) === t
          return `<button class="tier-btn tier-${t}${on ? ' on' : ''}" data-label="${label}" data-tier="${t}"
            ${locked ? 'disabled' : ''} aria-pressed="${on}">${TIER_NAMES[t]}</button>`
        })
        .join('')
      return `<div class="tier-row"><span class="tier-name tier-text-${tierOf(label)}">${LABEL_NAMES[label]}${
        locked ? ' <small>(always critical)</small>' : ''
      }</span><span class="tier-picker">${buttons}</span></div>`
    }).join('')
  }
  root.addEventListener('click', e => {
    const btn = (e.target as HTMLElement).closest<HTMLButtonElement>('button[data-label]')
    if (!btn || btn.disabled) return
    setTier(btn.dataset.label as (typeof LABELS)[number], btn.dataset.tier as Tier)
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
  // Cue brand: sun-on-haze background, black ink, one accent. Lens mirror stays dark with HUD green.
  const css = `
    :root { color-scheme: light; }
    html, body { margin: 0; min-height: 100%; color: #000000;
      background: linear-gradient(135deg, #d3dbe8 0%, #eef1f5 100%) fixed;
      font: 16px/1.4 -apple-system, BlinkMacSystemFont, 'Helvetica Neue', system-ui, sans-serif;
      touch-action: manipulation; -webkit-text-size-adjust: 100%;
      overscroll-behavior: none; }
    #app { display: flex; }
    .panel { display: flex; flex-direction: column; gap: 16px;
      width: 100%; max-width: 640px; margin: 0 auto; padding: 24px; box-sizing: border-box; }
    header { display: flex; align-items: center; justify-content: space-between;
      border-top: 4px solid #f2b64c; padding-top: 12px; }
    h1 { font-size: 20px; font-weight: 500; margin: 0; font-family: Georgia, 'Times New Roman', serif; }
    .status { font-size: 12px; padding: 4px 10px; border-radius: 999px;
      border: 1px solid #c5cdd9; letter-spacing: 0.04em; text-transform: uppercase; color: #4a5262; }
    .status-listening  { color: #000000; border-color: #000000; }
    .status-paused     { color: #4a5262; }
    .status-error      { color: #b3261e; border-color: #b3261e; }
    .transcript { overflow: auto; background: #1a1d1a; border: 1px solid #1a1d1a; color: #5ee07a;
      font-family: ui-monospace, 'SF Mono', Menlo, monospace;
      border-radius: 12px; padding: 20px; font-size: 18px; line-height: 1.5;
      min-height: 120px; white-space: pre-wrap; word-break: break-word; }
    .transcript .label { color: #7a847a; }
    .interim { color: #2f5a3a; font-size: 14px; }
    .label { font-size: 11px; color: #4a5262; text-transform: uppercase; letter-spacing: 0.08em; margin-top: 8px; }
    footer { font-size: 12px; color: #4a5262; text-align: center; }
    .tier-text-critical { color: #5ee07a; font-weight: 600; }
    .tier-text-medium { color: #5ee07a; }
    .tier-text-normal { color: #2f5a3a; }
    .tiers { border-top: 1px solid #c5cdd9; padding: 16px 0 0; }
    .tiers .tier-text-critical, .tiers .tier-text-medium { color: #000000; }
    .tiers .tier-text-normal { color: #4a5262; }
    .hint { font-size: 12px; color: #4a5262; margin: 4px 0 12px; }
    .tier-row { display: flex; align-items: center; justify-content: space-between; gap: 8px;
      padding: 8px 0; border-top: 1px solid #c5cdd9; flex-wrap: wrap; }
    .tier-name { font-size: 15px; }
    .tier-name small { color: #4a5262; font-weight: 400; }
    .tier-picker { display: flex; gap: 4px; }
    .tier-btn { font: inherit; font-size: 12px; padding: 6px 10px; border-radius: 999px;
      border: 1px solid #c5cdd9; background: transparent; color: #4a5262; }
    .tier-btn:disabled { opacity: 0.4; }
    .tier-btn.on:disabled { opacity: 1; }
    .tier-btn.on { color: #000000; border-color: #000000; background: rgba(0,0,0,0.06); }
  `
  const style = document.createElement('style')
  style.textContent = css
  document.head.appendChild(style)
}
