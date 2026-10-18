// Copyright 2022 The TensorFlow Authors. All Rights Reserved.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
// http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import TensorFlowLiteTaskAudio

/// Delegate to returns the classification results.
protocol AudioClassificationHelperDelegate: AnyObject {
  func audioClassificationHelper(_ helper: AudioClassificationHelper, didSucceed result: Result)
  func audioClassificationHelper(_ helper: AudioClassificationHelper, didFail error: Error)
}

private let errorDomain = "org.tensorflow.lite.examples"

/// Stores results for a particular audio snipprt that was successfully classified.
struct Result {
  let inferenceTime: Double
  let categories: [ClassificationCategory]
  /// `ts` of the newest glasses audio frame in the window; nil for the phone mic.
  var audioTs: Int64? = nil
}

/// Where the audio comes from.
enum InputSource: String {
  /// This phone's own microphone (the original sample app).
  case microphone
  /// The G2 glasses, streamed in through the Earshot laptop hub (`append(samples:ts:)`).
  case network
}

/// Information about a model file.
typealias FileInfo = (name: String, extension: String)

/// This class handles all data preprocessing and makes calls to run inference on a audio snippet
/// by invoking the Task Library's `AudioClassifier`.
class AudioClassificationHelper {

  // MARK: Public properties

  weak var delegate: AudioClassificationHelperDelegate?

  // MARK: Private properties

  /// An `AudioClassifier` object for performing audio classification using a given model.
  private let classifier: AudioClassifier

  /// An object to continously record audio using the device's microphone. Nil for `.network`.
  private let audioRecord: AudioRecord?

  private let inputSource: InputSource

  /// `.network` only: the newest `bufferSize` samples from the glasses, newest last.
  /// Touched only on `processQueue`.
  private var networkSamples: [Float] = []
  private var networkTs: Int64?
  private var networkLastAudio = Date.distantPast
  private var networkFresh = false
  private let glassesFilter = GlassesAudioFilter()

  /// A tensor to store the input audio for the model.
  private let inputAudioTensor: AudioTensor

  /// A timer to schedule classification routine to run periodically.
  private var timer: Timer?

  /// A queue to offload the classification routine to a background thread.
  private let processQueue = DispatchQueue(label: "processQueue")

  // MARK: - Initialization

  /// A failable initializer for `AudioClassificationHelper`.
  ///
  /// A new instance is created if the model is successfully loaded from the app's main bundle.
  init?(
    modelType: ModelType, threadCount: Int, scoreThreshold: Float, maxResults: Int,
    inputSource: InputSource = .microphone
  ) {
    self.inputSource = inputSource
    let modelFilename = modelType.fileName

    // Construct the path to the model file.
    guard
      let modelPath = Bundle.main.path(
        forResource: modelFilename,
        ofType: "tflite"
      )
    else {
      print("Failed to load the model file \(modelFilename).tflite.")
      return nil
    }

    // Specify the options for the classifier.
    let classifierOptions = AudioClassifierOptions(modelPath: modelPath)
    classifierOptions.baseOptions.computeSettings.cpuSettings.numThreads = threadCount
    classifierOptions.classificationOptions.maxResults = maxResults
    classifierOptions.classificationOptions.scoreThreshold = scoreThreshold

    do {
      // Create the classifier.
      classifier = try AudioClassifier.classifier(options: classifierOptions)

      // Create an `AudioRecord` instance to record input audio that satisfies
      // the model's requirements.
      audioRecord = inputSource == .microphone ? try classifier.createAudioRecord() : nil
      inputAudioTensor = classifier.createInputAudioTensor()
    } catch {
      print("Failed to create the classifier with error: \(error.localizedDescription)")
      return nil
    }
  }

  func stopClassifier() {
    audioRecord?.stop()
    timer?.invalidate()
    timer = nil
  }

  /// Start the audio classification routine in the background.
  ///
  /// Classification results are periodically returned to the delegate.
  /// - Parameters overlap: Overlapping factor between consecutive audio snippet to be classified.
  ///   Value must be >= 0 and < 1.
  func startClassifier(overlap: Double) {
    if overlap < 0 {
      let error = NSError(
        domain: errorDomain,
        code: 0,
        userInfo: [NSLocalizedDescriptionKey: "overlap must be equal or larger than 0."])
      delegate?.audioClassificationHelper(self, didFail: error)
    }

    if overlap >= 1 {
      let error = NSError(
        domain: errorDomain, code: 0,
        userInfo: [NSLocalizedDescriptionKey: "overlap must be smaller than 1."])
      delegate?.audioClassificationHelper(self, didFail: error)
    }

    do {
      // Start recording audio.
      try audioRecord?.startRecording()

      // Calculate interval between sampling based on overlap.
      let audioFormat = inputAudioTensor.audioFormat
      let lengthInMilliSeconds =
        Double(inputAudioTensor.bufferSize) / Double(audioFormat.sampleRate)
      let interval = lengthInMilliSeconds * Double(1 - overlap)
      timer?.invalidate()

      // Schedule the classification routine to run every fixed interval.
      timer = Timer.scheduledTimer(withTimeInterval: interval, repeats: true) {
        [weak self] _ in
        self?.processQueue.async {
          self?.runClassification()
        }
      }
    } catch {
      delegate?.audioClassificationHelper(self, didFail: error)
    }
  }

  /// `.network` only: add one frame of glasses audio (samples in -1...1). Any thread.
  func append(samples: [Float], ts: Int64?) {
    processQueue.async {
      let size = Int(self.inputAudioTensor.bufferSize)
      self.networkSamples.append(contentsOf: self.glassesFilter.highPass(samples))
      if self.networkSamples.count > size {
        self.networkSamples.removeFirst(self.networkSamples.count - size)
      }
      self.networkTs = ts
      self.networkLastAudio = Date()
      self.networkFresh = true
    }
  }

  /// Copy the glasses audio into the input tensor, zero-padded at the front until the
  /// buffer has filled. False if no new audio arrived since the last run, so a stalled
  /// stream sends nothing instead of repeating the last result.
  private func loadNetworkAudio() throws -> Bool {
    guard networkFresh, Date().timeIntervalSince(networkLastAudio) < 1 else { return false }
    networkFresh = false
    let size = Int(inputAudioTensor.bufferSize)
    let buffer = TFLFloatBuffer(size: UInt(size))
    let offset = size - networkSamples.count
    let window = GlassesAudioFilter.normalize(networkSamples)
    for (i, s) in window.enumerated() { buffer.data[offset + i] = s }
    try inputAudioTensor.load(buffer: buffer, offset: 0, size: UInt(size))
    return true
  }

  /// Run the classification routine with the latest audio stored in the `AudioRecord` instance's
  /// buffer, or the glasses audio for `.network`.
  private func runClassification() {
    let startTime = Date().timeIntervalSince1970
    do {
      var audioTs: Int64? = nil
      if let audioRecord = audioRecord {
        // Grab the latest audio chunk in the audio record and run classification.
        try inputAudioTensor.load(audioRecord: audioRecord)
      } else {
        guard try loadNetworkAudio() else { return }
        audioTs = networkTs
      }
      let results = try classifier.classify(audioTensor: inputAudioTensor)
      let inferenceTime = Date().timeIntervalSince1970 - startTime

      // Return the classification result to the delegate.
      DispatchQueue.main.async {
        let result = Result(
          inferenceTime: inferenceTime,
          categories: results.classifications[0].categories,
          audioTs: audioTs)
        // Send classification result to the delegate.
        self.delegate?.audioClassificationHelper(self, didSucceed: result)
      }
    } catch {
      DispatchQueue.main.async { self.delegate?.audioClassificationHelper(self, didFail: error) }
    }
  }
}

/// Cleans up G2 mic audio before YAMNet. Mirrors server/preprocess.py; keep the numbers in sync.
///
/// The G2 stream is dominated by rumble below 300 Hz, about 35 dB louder than the 1 to 4 kHz band
/// where alarms, sirens and doorbells live, so raw it classifies as Music/Throbbing/Hum. Two
/// Butterworth high-pass biquads at 600 Hz, then per-window gain to a target RMS, capped so
/// silence is not blown up into noise.
final class GlassesAudioFilter {
  static let cutoffHz = 600.0
  static let stages = 2
  static let targetRMS: Float = 0.05
  static let maxGain: Float = 30

  private let b0, b1, b2, a1, a2: Double
  /// Per stage: x1, x2, y1, y2. Carried across frames, so feed every frame in order.
  private var state: [[Double]]

  init(sampleRate: Double = 16000) {
    let w0 = 2 * Double.pi * Self.cutoffHz / sampleRate
    let alpha = sin(w0) / (2 * (1 / 2.0.squareRoot()))
    let c = cos(w0)
    let a0 = 1 + alpha
    b0 = (1 + c) / 2 / a0
    b1 = -(1 + c) / a0
    b2 = (1 + c) / 2 / a0
    a1 = -2 * c / a0
    a2 = (1 - alpha) / a0
    state = Array(repeating: [0, 0, 0, 0], count: Self.stages)
  }

  func highPass(_ input: [Float]) -> [Float] {
    var y = input.map(Double.init)
    for s in 0..<state.count {
      var (x1, x2, y1, y2) = (state[s][0], state[s][1], state[s][2], state[s][3])
      for i in 0..<y.count {
        let v = y[i]
        let o = b0 * v + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2 = x1; x1 = v; y2 = y1; y1 = o
        y[i] = o
      }
      state[s] = [x1, x2, y1, y2]
    }
    return y.map(Float.init)
  }

  static func normalize(_ window: [Float]) -> [Float] {
    guard !window.isEmpty else { return window }
    let rms = (window.reduce(0) { $0 + $1 * $1 } / Float(window.count)).squareRoot() + 1e-9
    let gain = min(maxGain, targetRMS / rms)
    return window.map { max(-1, min(1, $0 * gain)) }
  }
}
