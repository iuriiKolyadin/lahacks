// Puts the YAMNet model and MediaPipe's WASM runtime into public/, so they are
// served by the dev server and bundled into dist/ (and the .ehpk) by the build.
// Safe to run repeatedly: files that already exist are left alone.
import { copyFileSync, existsSync, mkdirSync, statSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const MODEL_URL = 'https://storage.googleapis.com/mediapipe-models/audio_classifier/yamnet/float32/1/yamnet.tflite'
const modelPath = join(root, 'public', 'models', 'yamnet.tflite')

// Only the SIMD build is shipped (Android WebView and iOS 16.4+ support WASM SIMD).
// The non-SIMD and module variants would add ~6.8 MB to a package with a ~10 MB practical cap.
const WASM_FILES = ['audio_wasm_internal.js', 'audio_wasm_internal.wasm']
const wasmSrc = join(root, 'node_modules', '@mediapipe', 'tasks-audio', 'wasm')
const wasmDst = join(root, 'public', 'wasm')

mkdirSync(dirname(modelPath), { recursive: true })
mkdirSync(wasmDst, { recursive: true })

if (!existsSync(modelPath)) {
  console.log(`[assets] downloading ${MODEL_URL}`)
  const res = await fetch(MODEL_URL)
  if (!res.ok) throw new Error(`model download failed: HTTP ${res.status}`)
  writeFileSync(modelPath, Buffer.from(await res.arrayBuffer()))
}
console.log(`[assets] model ok (${(statSync(modelPath).size / 1e6).toFixed(1)} MB)`)

for (const f of WASM_FILES) {
  const src = join(wasmSrc, f)
  const dst = join(wasmDst, f)
  if (!existsSync(src)) throw new Error(`missing ${src}; run npm install first`)
  if (!existsSync(dst) || statSync(dst).size !== statSync(src).size) copyFileSync(src, dst)
}
console.log('[assets] wasm ok')
