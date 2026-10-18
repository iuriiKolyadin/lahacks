import { waitForEvenAppBridge, type EvenAppBridge } from '@evenrealities/even_hub_sdk'
import { log } from './log'

// Resolves to the Even app bridge, or null when the page runs in a normal
// desktop browser (no Even app around it). Null means "browser mode": the HUD
// is drawn only on the page and audio comes from test clips.
//
// waitForEvenAppBridge() resolves even in a plain browser, so the host is
// detected by the native handler the SDK calls into (README: "Runtime: Even
// App WebView with window.flutter_inappwebview.callHandler").
export async function connectBridge(): Promise<EvenAppBridge | null> {
  const host = (window as unknown as { flutter_inappwebview?: { callHandler?: unknown } }).flutter_inappwebview
  if (typeof host?.callHandler !== 'function') {
    log('bridge', 'no Even app host found, browser mode')
    return null
  }
  const bridge = await waitForEvenAppBridge()
  log('bridge', 'connected to Even app')
  return bridge
}
