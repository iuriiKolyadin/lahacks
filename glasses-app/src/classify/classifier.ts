// The one interface the rest of the app sees. Any backend (MediaPipe YAMNet in
// the page, a fake for tests, a remote server) implements this.

export interface Score {
  /** Raw model class name, e.g. "Doorbell" (AudioSet display name for YAMNet). */
  label: string
  score: number
}

export interface Classifier {
  readonly name: string
  /** Mono audio at `sampleRate`, values in -1..1. Returns top scores, best first. */
  classify(window: Float32Array, sampleRate: number): Score[]
}
