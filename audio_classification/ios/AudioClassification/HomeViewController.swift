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

import AVFoundation
import TensorFlowLiteTaskAudio
import UIKit

/// The sample app's home screen.
class HomeViewController: UIViewController {

  // MARK: - Variables

  @IBOutlet private weak var tableView: UITableView!
  @IBOutlet private weak var inferenceView: InferenceView!

  private var inferenceResults: [ClassificationCategory] = []

  private var modelType: ModelType = .Yamnet
  private var overLap = 0.5
  // Earshot: the laptop hub applies its own per-label thresholds, so send it the top 10 unfiltered.
  private var maxResults = 10
  private var threshold: Float = 0.0
  private var threadCount = 2

  private var audioClassificationHelper: AudioClassificationHelper?

  // MARK: - Earshot

  private let defaults = UserDefaults.standard
  private var inputSource: InputSource {
    get { InputSource(rawValue: defaults.string(forKey: "inputSource") ?? "") ?? .network }
    set { defaults.set(newValue.rawValue, forKey: "inputSource") }
  }
  private var serverURL: String {
    get { defaults.string(forKey: "serverURL") ?? EarshotLink.defaultURL }
    set { defaults.set(newValue, forKey: "serverURL") }
  }
  private lazy var link: EarshotLink = {
    let link = EarshotLink(url: URL(string: serverURL) ?? URL(string: EarshotLink.defaultURL)!)
    link.delegate = self
    return link
  }()
  private let statusLabel = UILabel()
  private var linkStatus = "Not connected"
  private var framesThisSecond = 0
  private var resultsThisSecond = 0
  private var statsTimer: Timer?

  // MARK: - View controller lifecycle methods
  override func viewDidLoad() {
    super.viewDidLoad()
    inferenceView.setDefault(
      model: modelType, overLab: overLap, maxResult: maxResults, threshold: threshold,
      threads: threadCount)
    inferenceView.delegate = self
    // Earshot runs plugged in on a table; the socket dies if the phone locks.
    UIApplication.shared.isIdleTimerDisabled = true
    setUpStatusHeader()
    NotificationCenter.default.addObserver(
      self, selector: #selector(willEnterForeground),
      name: UIApplication.willEnterForegroundNotification, object: nil)
    statsTimer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in
      self?.refreshStatus()
    }
    startAudioClassification()
  }

  @objc private func willEnterForeground() {
    link.reconnect()
  }

  private func setUpStatusHeader() {
    statusLabel.numberOfLines = 0
    statusLabel.font = .monospacedSystemFont(ofSize: 13, weight: .regular)
    statusLabel.textAlignment = .center
    statusLabel.isUserInteractionEnabled = true
    statusLabel.addGestureRecognizer(
      UITapGestureRecognizer(target: self, action: #selector(showSettings)))
    statusLabel.frame = CGRect(x: 0, y: 0, width: tableView.bounds.width, height: 72)
    tableView.tableHeaderView = statusLabel
    refreshStatus()
  }

  private func refreshStatus() {
    let source = inputSource == .network ? "Glasses audio" : "Phone mic"
    var lines = [source, linkStatus]
    if inputSource == .network {
      lines.append("\(framesThisSecond) frames/s in · \(resultsThisSecond) results/s out")
    } else {
      lines.append("\(resultsThisSecond) results/s out")
    }
    lines.append("Tap to change")
    statusLabel.text = lines.joined(separator: "\n")
    framesThisSecond = 0
    resultsThisSecond = 0
  }

  @objc private func showSettings() {
    let alert = UIAlertController(
      title: "Earshot", message: "Laptop hub address (ws://LAPTOP_IP:8000/ws/classifier)",
      preferredStyle: .alert)
    alert.addTextField { field in
      field.text = self.serverURL
      field.keyboardType = .URL
      field.autocapitalizationType = .none
      field.autocorrectionType = .no
    }
    // Both modes send results to the hub; they differ only in where the audio comes from.
    func apply(_ source: InputSource) {
      let text = alert.textFields?.first?.text?.trimmingCharacters(in: .whitespaces) ?? ""
      if let url = URL(string: text), url.scheme == "ws" || url.scheme == "wss" {
        serverURL = text
      }
      inputSource = source
      link.reconnect(to: URL(string: serverURL))
      startAudioClassification()
      refreshStatus()
    }
    alert.addAction(UIAlertAction(title: "Use glasses audio", style: .default) { _ in apply(.network) })
    alert.addAction(UIAlertAction(title: "Use phone mic", style: .default) { _ in apply(.microphone) })
    alert.addAction(UIAlertAction(title: "Cancel", style: .cancel))
    present(alert, animated: true)
  }

  // MARK: - Private Methods
  /// Request permission and start audio classification if granted.
  private func startAudioClassification() {
    link.start()
    // Glasses audio needs no mic permission.
    if inputSource == .network {
      restartClassifier()
      return
    }
    AVAudioSession.sharedInstance().requestRecordPermission { [weak self] granted in
      if granted {
        DispatchQueue.main.async {
          self?.restartClassifier()
        }
      } else {
        self?.checkPermissions()
      }
    }
  }

  /// Check permission and show error if user denied permission.
  private func checkPermissions() {
    switch AVAudioSession.sharedInstance().recordPermission {
    case .granted, .undetermined:
      startAudioClassification()
    case .denied:
      showPermissionsErrorAlert()
    @unknown default:
      fatalError("Microphone permission check returned unexpected result.")
    }
  }

  /// Start a new audio classification routine.
  private func restartClassifier() {
    // Stop the existing classifier if one is running.
    audioClassificationHelper?.stopClassifier()

    // Create a new classifier instance.
    audioClassificationHelper = AudioClassificationHelper(
      modelType: modelType,
      threadCount: threadCount,
      scoreThreshold: threshold,
      maxResults: maxResults,
      inputSource: inputSource)

    // Start the new classification routine.
    audioClassificationHelper?.delegate = self
    audioClassificationHelper?.startClassifier(overlap: overLap)
  }
}

extension HomeViewController {
  private func showPermissionsErrorAlert() {
    let alertController = UIAlertController(
      title: "Microphone Permissions Denied",
      message:
        "Microphone permissions have been denied for this app. You can change this by going to Settings",
      preferredStyle: .alert
    )

    let cancelAction = UIAlertAction(title: "Cancel", style: .cancel, handler: nil)
    let settingsAction = UIAlertAction(title: "Settings", style: .default) { _ in
      UIApplication.shared.open(
        URL(string: UIApplication.openSettingsURLString)!,
        options: [:],
        completionHandler: nil
      )
    }
    alertController.addAction(cancelAction)
    alertController.addAction(settingsAction)

    present(alertController, animated: true, completion: nil)
  }
}

enum ModelType: String {
  case Yamnet = "YAMNet"
  case speechCommandModel = "Speech Command"

  var fileName: String {
    switch self {
    case .Yamnet:
      return "yamnet"
    case .speechCommandModel:
      return "speech_commands"
    }
  }
}

extension HomeViewController: UITableViewDataSource, UITableViewDelegate {

  func tableView(_ tableView: UITableView, cellForRowAt indexPath: IndexPath) -> UITableViewCell {
    guard
      let cell = tableView.dequeueReusableCell(withIdentifier: "ResultCell") as? ResultTableViewCell
    else { fatalError() }
    cell.setData(inferenceResults[indexPath.row])
    return cell
  }

  func tableView(_ tableView: UITableView, numberOfRowsInSection section: Int) -> Int {
    return inferenceResults.count
  }
}

extension HomeViewController: AudioClassificationHelperDelegate {
  func audioClassificationHelper(_ helper: AudioClassificationHelper, didSucceed result: Result) {
    inferenceResults = result.categories
    tableView.reloadData()
    // Phone mic results carry no audio ts; the hub shows them on the glasses all the same.
    link.send(result)
    resultsThisSecond += 1
    inferenceView.setInferenceTime(result.inferenceTime)
  }

  func audioClassificationHelper(_ helper: AudioClassificationHelper, didFail error: Error) {
    let errorMessage =
      "An error occured while running audio classification: \(error.localizedDescription)"
    let alert = UIAlertController(
      title: "Error", message: errorMessage, preferredStyle: UIAlertController.Style.alert)
    alert.addAction(UIAlertAction(title: "OK", style: UIAlertAction.Style.default, handler: nil))
    present(alert, animated: true, completion: nil)
  }
}

extension HomeViewController: InferenceViewDelegate {
  func view(_ view: InferenceView, needPerformActions action: InferenceView.Action) {
    switch action {
    case .changeModel(let modelType):
      self.modelType = modelType
    case .changeOverlap(let overLap):
      self.overLap = overLap
    case .changeMaxResults(let maxResults):
      self.maxResults = maxResults
    case .changeScoreThreshold(let threshold):
      self.threshold = threshold
    case .changeThreadCount(let threadCount):
      self.threadCount = threadCount
    }

    // Restart the audio classifier as the config as changed.
    restartClassifier()
  }
}

extension HomeViewController: EarshotLinkDelegate {
  func earshotLink(_ link: EarshotLink, didReceive samples: [Float], ts: Int64?) {
    // In phone-mic mode the hub still forwards glasses audio; ignore it.
    guard inputSource == .network else { return }
    audioClassificationHelper?.append(samples: samples, ts: ts)
    DispatchQueue.main.async { self.framesThisSecond += 1 }
  }

  func earshotLink(_ link: EarshotLink, didChangeStatus status: String) {
    linkStatus = status
  }
}
