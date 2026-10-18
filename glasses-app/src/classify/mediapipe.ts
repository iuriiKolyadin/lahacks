import { AudioClassifier } from '@mediapipe/tasks-audio'
import type { Classifier, Score } from './classifier'
import { log } from '../log'

// YAMNet (same weights as YAMNet_audio_classification.ipynb, TFLite build) run
// by MediaPipe's WASM audio classifier inside the page. Model and WASM ship in
// the app bundle; nothing is fetched from the internet at runtime.
export async function createMediaPipeClassifier(topK = 5): Promise<Classifier> {
  const base = new URL('./', document.baseURI).href
  const fileset = {
    wasmLoaderPath: `${base}wasm/audio_wasm_internal.js`,
    wasmBinaryPath: `${base}wasm/audio_wasm_internal.wasm`,
  }
  const t = performance.now()
  const mp = await AudioClassifier.createFromOptions(fileset, {
    baseOptions: { modelAssetPath: `${base}models/yamnet.tflite` },
    maxResults: topK,
  })
  log('model', `YAMNet loaded in ${Math.round(performance.now() - t)} ms`)

  return {
    name: 'mediapipe-yamnet',
    classify(window, sampleRate) {
      // YAMNet scores 0.975 s patches (15600 samples at 16 kHz). Longer input is
      // split into several results and the last one is mostly zero padding
      // (a 1.0 s tone came back as "Beep" then "Silence"), so use the first.
      const results = mp.classify(window, sampleRate)
      const cats = results[0]?.classifications[0]?.categories ?? []
      return cats.map((c): Score => ({ label: c.categoryName || c.displayName, score: c.score }))
    },
  }
}
