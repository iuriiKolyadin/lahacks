// WebSocket link to the Earshot server (PRD.md section 5).
//
// Up:   one frame per glasses audio event
//       {"t":"audio","pcm":<base64 int16 LE>,"direction":int|null,"speakerRole":"self"|"other"|"unknown","ts":ms}
//       plus "alert" frames for the phone (alerts.ts), which the server relays to /ws/pendant
// Down: one frame per HUD state change
//       {"state","label","dir","ttl_ms","level"}
//
// Audio arriving while the socket is down is dropped, not queued: a stale
// doorbell is worse than a missed one. Reconnects 1 s after any close.

import type { AudioEvent } from '@evenrealities/even_hub_sdk'

export type HudState = {
  state: 'idle' | 'cue' | 'speech' | 'name' | 'alarm'
  label?: 'doorbell' | 'knock' | 'siren' | 'alarm' | 'horn' | 'dog' | 'clap' | 'snap' | 'speech' | 'name'
  dir?: 'left' | 'right' | 'front' | 'behind' | 'center' | 'near'
  ttl_ms?: number
  level?: number
}

export type LinkStatus = 'connecting' | 'open' | 'closed'

export interface Link {
  sendAudio(audio: AudioEvent): void
  /** Send one JSON frame now. False (and dropped) if the socket is not open. */
  send(frame: object): boolean
  /** Drop the current socket (if any) and connect again now. */
  reconnect(): void
  close(): void
}

// Priority: ?server=ws://host:8000/ws/glasses, then VITE_SERVER_URL at build
// time, then port 8000 on whatever host served this page (the dev laptop).
export function serverUrl(): string {
  const fromQuery = new URLSearchParams(location.search).get('server')
  if (fromQuery) return fromQuery
  const fromEnv = import.meta.env.VITE_SERVER_URL as string | undefined
  if (fromEnv) return fromEnv
  return `ws://${location.hostname || 'localhost'}:8000/ws/glasses`
}

// btoa needs a binary string; build it in chunks so large frames don't blow the call stack.
function toBase64(bytes: Uint8Array): string {
  let bin = ''
  for (let i = 0; i < bytes.length; i += 0x8000) {
    bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000))
  }
  return btoa(bin)
}

export function startLink(
  url: string,
  onState: (state: HudState) => void,
  onStatus: (status: LinkStatus) => void = () => {},
): Link {
  let ws: WebSocket | null = null
  let retry: number | null = null
  let closed = false

  function connect() {
    if (closed) return
    if (retry !== null) {
      clearTimeout(retry)
      retry = null
    }
    onStatus('connecting')
    const sock = new WebSocket(url)
    ws = sock
    sock.onopen = () => onStatus('open')
    sock.onmessage = msg => {
      try {
        onState(JSON.parse(msg.data as string) as HudState)
      } catch (err) {
        console.warn('Bad state frame:', msg.data, err)
      }
    }
    sock.onclose = () => {
      if (ws !== sock) return // replaced by reconnect()
      ws = null
      onStatus('closed')
      if (!closed) retry = window.setTimeout(connect, 1000)
    }
    sock.onerror = () => sock.close()
  }

  connect()

  return {
    sendAudio(audio) {
      if (ws?.readyState !== WebSocket.OPEN) return
      ws.send(
        JSON.stringify({
          t: 'audio',
          pcm: toBase64(audio.audioPcm),
          direction: audio.direction ?? null,
          speakerRole: audio.speakerRole ?? 'unknown',
          ts: Date.now(),
        }),
      )
    },
    send(frame) {
      if (ws?.readyState !== WebSocket.OPEN) return false
      ws.send(JSON.stringify(frame))
      return true
    },
    reconnect() {
      const old = ws
      ws = null
      old?.close()
      connect()
    },
    close() {
      closed = true
      if (retry !== null) clearTimeout(retry)
      const old = ws
      ws = null
      old?.close()
    },
  }
}
