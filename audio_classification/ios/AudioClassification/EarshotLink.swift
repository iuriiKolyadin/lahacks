import Foundation

/// Receives the G2 glasses' audio from the Cue laptop hub and sends YAMNet results back.
///
/// Down: {"t":"audio","pcm":"<base64 int16 LE, 16 kHz mono>","ts":<ms>, ...}, forwarded unchanged
///       from the plugin.
/// Up:   {"t":"result","ts":<ts of the newest audio>,"inference_ms":n,
///        "top":[{"label":"Doorbell","score":0.82}, ...]}
///
/// Reconnects 1 s after any failure.
protocol EarshotLinkDelegate: AnyObject {
  /// Called on the link's queue, once per audio frame, with samples in -1...1.
  func earshotLink(_ link: EarshotLink, didReceive samples: [Float], ts: Int64?)
  /// Called on the main queue.
  func earshotLink(_ link: EarshotLink, didChangeStatus status: String)
}

final class EarshotLink: NSObject, URLSessionWebSocketDelegate {

  static let defaultURL = "ws://172.20.10.3:8000/ws/classifier"

  weak var delegate: EarshotLinkDelegate?
  private(set) var url: URL

  private let queue = OperationQueue()
  private lazy var session = URLSession(configuration: .default, delegate: self, delegateQueue: queue)
  private var task: URLSessionWebSocketTask?
  private var running = false

  init(url: URL) {
    self.url = url
    super.init()
    queue.maxConcurrentOperationCount = 1
  }

  func start() {
    queue.addOperation {
      self.running = true
      self.connect()
    }
  }

  func stop() {
    queue.addOperation {
      self.running = false
      self.task?.cancel(with: .goingAway, reason: nil)
      self.task = nil
    }
  }

  /// Drop the socket and connect again, optionally to a new address.
  func reconnect(to newURL: URL? = nil) {
    queue.addOperation {
      if let newURL = newURL { self.url = newURL }
      self.task?.cancel(with: .goingAway, reason: nil)
      self.task = nil
      self.running = true
      self.connect()
    }
  }

  func send(_ result: Result) {
    var frame: [String: Any] = [
      "t": "result",
      "inference_ms": Int(result.inferenceTime * 1000),
      "top": result.categories.map { c in
        ["label": c.label ?? c.displayName ?? "", "score": c.score] as [String: Any]
      },
    ]
    if let ts = result.audioTs { frame["ts"] = ts }
    guard let data = try? JSONSerialization.data(withJSONObject: frame),
      let text = String(data: data, encoding: .utf8)
    else { return }
    queue.addOperation {
      self.task?.send(.string(text)) { _ in }
    }
  }

  // MARK: - Private, all on `queue`

  private func connect() {
    guard running, task == nil else { return }
    report("Connecting · \(url.absoluteString)")
    let t = session.webSocketTask(with: url)
    t.maximumMessageSize = 4 * 1024 * 1024
    task = t
    t.resume()
    receive(on: t)
  }

  private func receive(on t: URLSessionWebSocketTask) {
    t.receive { [weak self] outcome in
      guard let self = self, self.task === t else { return }
      switch outcome {
      case .success(let message):
        if case .string(let text) = message { self.handle(text) }
        self.receive(on: t)
      case .failure(let error):
        self.dropped(t, why: error.localizedDescription)
      }
    }
  }

  private func handle(_ text: String) {
    guard let data = text.data(using: .utf8),
      let msg = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
      msg["t"] as? String == "audio",
      let b64 = msg["pcm"] as? String,
      let pcm = Data(base64Encoded: b64)
    else { return }
    var samples = [Float](repeating: 0, count: pcm.count / 2)
    pcm.withUnsafeBytes { (raw: UnsafeRawBufferPointer) in
      for i in 0..<samples.count {
        let s = Int16(bitPattern: UInt16(raw[2 * i]) | UInt16(raw[2 * i + 1]) << 8)
        samples[i] = Float(s) / 32768
      }
    }
    let ts = (msg["ts"] as? NSNumber)?.int64Value
    delegate?.earshotLink(self, didReceive: samples, ts: ts)
  }

  private func dropped(_ t: URLSessionWebSocketTask, why: String) {
    guard task === t else { return }
    task = nil
    report("Disconnected, retrying · \(why)")
    guard running else { return }
    DispatchQueue.global().asyncAfter(deadline: .now() + 1) { [weak self] in
      self?.queue.addOperation { self?.connect() }
    }
  }

  private func report(_ status: String) {
    DispatchQueue.main.async { self.delegate?.earshotLink(self, didChangeStatus: status) }
  }

  // MARK: - URLSessionWebSocketDelegate

  func urlSession(
    _ session: URLSession, webSocketTask: URLSessionWebSocketTask,
    didOpenWithProtocol protocol: String?
  ) {
    guard webSocketTask === task else { return }
    report("Connected · \(url.absoluteString)")
  }

  func urlSession(
    _ session: URLSession, webSocketTask: URLSessionWebSocketTask,
    didCloseWith closeCode: URLSessionWebSocketTask.CloseCode, reason: Data?
  ) {
    dropped(webSocketTask, why: "closed (\(closeCode.rawValue))")
  }
}
