# Cue architecture

How a sound near the wearer becomes a line of text on the G2 lenses: the
devices, the WebSocket links, the YAMNet classifier, the noise filtering, the
direction estimate, and the rules that decide what reaches the HUD.

State of the code: Sun 2026-10-18 morning. File references are to this repo.

---

## 1. The big picture

Four devices, one hotspot, three WebSocket hops:

```
 ┌──────────────┐  Bluetooth   ┌────────────────────────────┐
 │  G2 glasses  │─────────────▶│  Glasses phone             │
 │  mics + HUD  │◀─────────────│  Even app + Cue plugin │
 └──────────────┘  PCM up,     │  (web page in a WebView)   │
                   text down   └─────────────┬──────────────┘
                                             │ ws://<laptop IPv4>:8000/ws/glasses
                                             │   up:   audio frames (+ direction tag)
                                             │   down: HUD state frames
                                             ▼
                               ┌────────────────────────────┐
                               │  Server laptop             │
                               │  server/main.py (hub)      │
                               │  labels, state machine,    │
                               │  direction tracker         │
                               └─────────────┬──────────────┘
                                             │ ws://[<laptop IPv6>]:8000/ws/classifier
                                             │   out:  the same audio frames, unchanged
                                             │   back: YAMNet top-10 scores per window
                                             ▼
                               ┌────────────────────────────┐
                               │  Classifier iPhone         │
                               │  AudioClassification app   │
                               │  high-pass + gain + YAMNet │
                               └────────────────────────────┘
```

Who does what:

| Piece | Code | Job |
|---|---|---|
| G2 glasses | firmware | Capture audio, estimate a direction angle per frame, show text |
| Plugin | `plugin/src/` (TypeScript, Vite) | Turn the mic on, forward every audio frame to the server, draw whatever state comes back |
| Hub | `server/main.py` | Fan audio out to the classifier, turn scores into HUD states, attach a direction |
| Classifier | `audio_classification/ios/` (Swift) | Clean up the audio, run YAMNet, send scores back |

Why split it this way: the plugin is a web page inside someone else's app, so
it should stay thin (receive, forward, draw). YAMNet runs on an iPhone because
that app already existed and runs the model in well under 100 ms. The laptop
sits in the middle because it is the easiest place to change rules quickly:
editing a Python file and restarting takes seconds, rebuilding an iOS app does
not.

A separate Android companion (`android-companion/`, `docs/BRIDGE.md`) handles
speaking replies for the wearer. It talks to the plugin on its own socket and
is not part of the sound path described here.

---

## 2. The WebSocket links

### 2.1 Why WebSockets

Every link is a long-lived, two-way, low-latency stream: audio goes one way
roughly 20 times a second and results come back whenever they are ready.
WebSockets give that over plain TCP with no polling, they work from a browser
WebView (the plugin), from Python (FastAPI/uvicorn), and from iOS
(`URLSessionWebSocketTask`). All frames are JSON text, one object per frame.

### 2.2 The messages

**Plugin → hub** (`/ws/glasses`), one per audio event from the glasses:

```json
{"t":"audio","pcm":"<base64>","direction":-17,"speakerRole":"other","ts":1760745600123}
```

- `pcm`: raw audio, signed 16-bit little-endian, 16 kHz, mono, base64. About
  800 samples (50 ms) per frame, about 20 frames a second.
- `direction`: the glasses' angle estimate for this frame (section 5), or null.
- `speakerRole`: the glasses' guess whether this is the wearer talking
  (`self`) or someone else (`other`).
- `ts`: the plugin's clock in ms. Used only to measure round-trip time.

**Hub → classifier** (`/ws/classifier`): the exact same text, forwarded
unchanged. The hub never decodes and re-encodes it on this path.

**Classifier → hub**, one per classified window (every ~0.5 s):

```json
{"t":"result","ts":1760745600123,"inference_ms":12,
 "top":[{"label":"Doorbell","score":0.82},{"label":"Ding-dong","score":0.41}, ...]}
```

`top` is YAMNet's 10 best classes by raw name, unfiltered. `ts` echoes the
newest audio frame in the window, so the hub can look up when it received that
frame and log the round trip (`RESULT rtt=...`).

**Hub → plugin** (`/ws/glasses`), only when what the HUD should show changes:

```json
{"state":"cue","label":"doorbell","dir":"right","ttl_ms":4000,"level":4}
```

- `state`: `idle`, `cue`, `speech`, `name`, `alarm`
- `label`: `doorbell`, `knock`, `siren`, `alarm`, `horn`, `dog`, `clap`, `snap`, `speech`, `name`
- `dir`: `left`, `right`, `center` (ahead or behind), `front`, `behind`, `near` (no arrow)
- `ttl_ms`: how long to show it; `0` means until the next frame
- `level`: legacy brightness hint; the plugin's tier settings decide instead

**`GET /`** on the hub returns a status JSON (who is connected, frame and
result counts, current state, last result, live direction angle). It is the
quickest health check from any device on the hotspot.

### 2.3 Inside the hub

`server/main.py` is one FastAPI app on uvicorn, one asyncio event loop:

- **One receive loop per socket.** `serve()` accepts the socket, adds it to a
  pool (`glasses` or `classifiers`), and handles each incoming text frame.
  Errors in handling one frame are logged, never allowed to close the socket.
- **One send queue per socket** (`Peer`). Sends go into a 32-frame queue that a
  separate task drains. If a receiver is slow, the oldest frame is dropped
  rather than blocking the loop. This matters: forwarding audio to a slow
  iPhone must never stall reading from the glasses.
- **A 100 ms tick** (`tick_loop`) asks the state machine what the HUD should
  show now and broadcasts only on change. Expiry (a cue ending after 4 s) comes
  from this tick, not from incoming audio.
- **`--mock`** replaces the tick with a loop that cycles every state every 5 s,
  so the plugin can be tested with no classifier.
- **`--dump file.jsonl`** writes each frame's direction tag and loudness, for
  `tools/dirtest.py`.

Audio that arrives while the classifier is disconnected is dropped, not
queued. A stale doorbell is worse than a missed one.

### 2.4 The network layer (what bit us)

- **Dual-stack listening.** Our hotspot is on T-Mobile, which gives some
  devices IPv6 only (a Mac shows the placeholder `192.0.0.2`). The hub opens
  two listening sockets, `0.0.0.0:8000` (IPv4) and `[::]:8000` (IPv6), and
  hands both to uvicorn (`listen_sockets()`). The plugin reaches the laptop
  over IPv4 (`172.20.10.3`); the classifier iPhone over IPv6
  (`ws://[2607:fb91:...]:8000`).
- **The IPv6 address changes.** T-Mobile rotates the hotspot's IPv6 prefix, so
  the laptop's `2607:` address changes with it, and the iPhone app must be
  given the new one (`ipconfig` on the laptop). The IPv4 address does not.
- **Windows firewall.** Inbound port 8000 must be opened by port
  (`netsh advfirewall ... localport=8000`), not by allowing `python.exe`: the
  venv's `python.exe` is a launcher, so the program rule can miss.
- **iOS App Transport Security.** iOS blocks plain `ws://` unless the app's
  `Info.plist` allows it. Only `NSAllowsArbitraryLoads` is set: on iOS 10+ it
  is silently ignored if `NSAllowsLocalNetworking` is also present, and that
  combination blocked the global IPv6 address.
- **The Even WebView** only lets the plugin open connections to origins listed
  in `plugin/app.json` (`network.whitelist`), exact match, no wildcards. A
  packed Beta build must list the laptop's address.

### 2.5 Reconnects

Every client reconnects 1 s after any close: the plugin (`plugin/src/link.ts`),
the iPhone app (`CueLink.swift`), and the test tools. The hub sends the
current state to a glasses socket as soon as it connects, so a reconnect
restores the HUD immediately. The iPhone app also reconnects when it comes
back to the foreground, and keeps the screen awake because iOS kills sockets
of backgrounded apps.

---

## 3. YAMNet, the classifier

### 3.1 What it is

YAMNet is a free audio event classifier from Google, trained on AudioSet
(about 2 million 10-second YouTube clips labelled with 521 sound classes:
"Speech", "Doorbell", "Siren", "Dog", "Vacuum cleaner", "Music", ...). It is
a MobileNet v1 convolutional network: small and fast enough for a phone.

How it sees sound:

1. Take **15,600 samples** at 16 kHz, which is **0.975 s** of audio, as floats
   from -1 to 1.
2. Turn it into a **log-mel spectrogram**: slice it into 25 ms frames every
   10 ms, measure the energy in 64 frequency bands spaced the way human
   hearing is (mel scale, 125 Hz to 7.5 kHz), take the log. The result is a
   96 x 64 image of time by pitch.
3. Run that image through the CNN, which outputs **521 scores**, one per
   class, each between 0 and 1. They are independent (sigmoid, not softmax),
   so several classes can be high at once: a doorbell clip can score
   "Doorbell 0.8" and "Ding-dong 0.4" and "Music 0.1".

A score is "how much this window looks like the class", not a calibrated
probability. That is why every threshold in this project was set from
measured clips, not picked from theory.

### 3.2 How we run it

The iPhone app is Google's TensorFlow Lite audio classification example,
modified. It ships `yamnet.tflite` (the model plus its 521 class names inside
the file) and uses the TFLite Task Library's `AudioClassifier`.

The original app records from the phone's own mic. Ours has a second input
source, glasses audio from the network
(`audio_classification/ios/AudioClassification/TFLite/AudioClassificationHelper.swift`):

1. `CueLink` receives each audio frame, base64-decodes it, converts int16
   to float (divide by 32,768).
2. The samples go through the high-pass filter (section 4) and into a rolling
   buffer holding the newest 15,600 samples.
3. A timer fires every ~0.49 s (the window length with 50% overlap). If new
   audio has arrived in the last second, the buffer is gain-normalized
   (section 4) and copied into the model's input tensor, and YAMNet runs.
   If no new audio arrived, nothing is sent, so a stalled stream goes quiet
   instead of repeating the last result.
4. The top 10 classes, with no score threshold, go back to the hub with the
   newest frame's `ts`.

So each window overlaps the previous one by half: a sound is usually seen by
two consecutive windows. Inference takes a few ms on the iPhone and 2 to 4 ms
on a laptop.

`server/fake_classifier.py --model .../yamnet.tflite` runs the same model with
the same preprocessing on a laptop (via `ai-edge-litert`), so everything can be
tested without the iPhone.

### 3.3 From 521 classes to our labels

`server/labels.py` maps 27 YAMNet classes onto 9 labels and ignores the rest:

| Label | YAMNet classes |
|---|---|
| `alarm` | Alarm, Smoke detector/smoke alarm, Fire alarm, Car alarm, Alarm clock |
| `siren` | Siren, Civil defense siren, Police car (siren), Ambulance (siren), Fire engine/fire truck (siren) |
| `doorbell` | Doorbell, Ding-dong |
| `knock` | Knock |
| `horn` | Vehicle horn/car horn/honking, Air horn/truck horn |
| `dog` | Dog, Bark, Bow-wow, Yip, Howl, Growling, Whimper (dog) |
| `clap` | Clapping |
| `snap` | Finger snapping |
| `speech` | Speech, Child speech, Conversation, Narration/monologue |

For each window the hub keeps the best score per label
(`scores_by_label()`). Everything else, including near-misses left out on
purpose (Tap, Honk, which is a goose, Bell, Buzzer, Beep, Door, Applause,
Speech synthesizer, crowd babble), never reaches the HUD.

---

## 4. Filtering noise

"Noise" means two different problems here, solved in two different places:

1. **The G2's audio is dominated by low rumble** that hides the sounds we
   want. Solved on the iPhone, before YAMNet, with signal processing.
2. **YAMNet guesses something for every window**, including room hiss, music,
   and brief misfires. Solved on the hub, after YAMNet, with decision rules.

### 4.1 What the glasses actually send

The first real recording through the G2 (a smoke alarm,
`plugin/recordings/alarm_1.wav`) showed:

| Frequency band | Level |
|---|---|
| below 300 Hz | about -29 dBFS |
| 300 Hz to 1 kHz | about -53 dBFS |
| 1 to 2 kHz | about -66 dBFS |
| 2 to 4 kHz (where alarms live) | about -72 dBFS |

99.9% of the energy was below 500 Hz. The alarm was there, but about 40 dB
under the rumble. Raw, YAMNet heard "Music, Throbbing, Hum, Heartbeat" and
never scored siren or alarm above 0.08. The SDK calls this stream "processed
PCM": it is tuned for speech, not for alarms.

### 4.2 High-pass filter

A high-pass filter removes everything below a cutoff and keeps everything
above. Ours (`GlassesAudioFilter` in Swift, mirrored in
`server/preprocess.py`):

- Cutoff **600 Hz**.
- Two Butterworth biquad stages in series. A biquad is the standard 2nd-order
  digital filter: each output sample is a weighted sum of the last 3 inputs
  and the last 2 outputs. Two stages make a 4th-order filter: the response
  falls 24 dB per octave below 600 Hz, so 150 Hz rumble is cut by about 48 dB.
- Streaming: the filter's memory (last inputs and outputs) carries across
  frames, so it can be fed 50 ms at a time with no clicks at frame edges.

Measured on the real alarm recording (31 half-second windows):

| Filter | Windows scoring alarm/siren ≥ 0.3 |
|---|---|
| none | 0 |
| 300 Hz, 1 stage | 0 |
| 400 Hz, 2 stages | 8 |
| **600 Hz, 2 stages** | **14** |
| 800 Hz, 2 stages | 16 |

600 Hz was chosen over 800 Hz to keep more of what makes knocks and speech
recognizable. The cost is real: Dara's eval (`docs/eval-2026-10-17.md`)
shows the 600 Hz filter takes studio knock clips from 3/3 to 0/3, because a
knock is mostly low frequency. Running YAMNet twice per window (filtered and
raw, best score per label) recovers them (13/22 → 19/22 clips) and is the
measured next step; the team decided not to change the app this close to the
deadline.

### 4.3 Gain normalization

After the filter, what is left is quiet (RMS around -50 dBFS). YAMNet's
log-mel features depend on level, so each 0.975 s window is scaled to a target
RMS of **0.05** (about -26 dBFS), with the gain capped at **10x** (+20 dB) and
the result clipped to ±1.

The cap is the noise trade-off. Without a cap, a silent room would be boosted
until its hiss filled the window, and YAMNet would report "Stream, Water,
Vacuum cleaner" (it did, at the earlier 30x cap). With 10x, quiet stays quiet.
Those hiss guesses never reached the HUD anyway, because none of them map to a
label, but the lower cap keeps the iPhone's live list readable and costs
nothing on alarms.

### 4.4 Decision rules on the hub

Every window's label scores go to `StateMachine.observe()` in
`server/state.py`. Four rules decide whether a label fires:

**1. Threshold per label.** The score must reach:

| Label | Threshold | Why |
|---|---|---|
| alarm, siren | 0.3 | Through the G2 a real alarm peaks at only 0.3 to 0.5 after filtering. Missing an alarm is the worst failure. |
| doorbell, knock, horn, clap, snap | 0.5 | Strict, so room noise does not leak through. |
| dog | 0.4 | Barks lose score through the G2 (clean 0.6 to 0.9, G2-like 0.3 to 0.6). |
| speech | 0.6 | Speech is everywhere at a venue; only clear speech counts. |

**2. k of the last n windows.** A label fires only when it passed its
threshold in `k` of its last `n` windows (`HITS` in `labels.py`):

| Label | Rule | Effect |
|---|---|---|
| most | 2 of 3 | About 1 s of sustained sound. One-window blips are dropped. |
| alarm, siren | 2 of 4 | Real alarms through the G2 are detected on and off; 2 of 4 shows ALARM at 2.5 s and holds it, where 2 of 3 came on late and blinked. |
| dog | 1 of 1 | A bark is short and usually scores in one window only; 2 of 3 dropped even a clean bark scored 0.85. |

**3. Cooldown.** After a cue starts, the same label cannot start a new cue for
5 s (3 s for clap and snap). One long doorbell ring is one cue, not a cue
every half second.

**4. Wearer's own voice.** Speech counts only when the glasses'
`speakerRole` is not `self`.

Dara's eval, 22 test clips plus 6 noise clips (vacuum cleaner, crying baby):
**zero false cues on noise under every setting.**

### 4.5 What the HUD shows, in priority order

1. **Alarm/siren**: holds until 3 s after the last detection and suppresses
   everything else while up (a doorbell during a fire alarm is dropped).
2. **Your name**: 4 s (needs the Porcupine keyword spotter, not built).
3. **Cue** (doorbell, knock, horn, dog, clap, snap): 4 s; a newer cue
   replaces an older one.
4. **Speech**: holds while detected, fades 3 s after the last detection.
5. **Idle**: blank.

---

## 5. Direction

### 5.1 What the glasses give us

The SDK documents `AudioEvent.direction` only as "raw glasses direction tag
... a signed int16" with unit and range unspecified, and Even's FAQ lists
direction reporting as "on the roadmap". We decoded it from data.

The values seen are always from this set:

```
-90  -66  -49  -37  -27  -17  -8  0  8  17  27  37  49  66  90
```

Those are `asin(k × 0.15)` in degrees for k = 0..6, plus ±90. That pattern is
the fingerprint of a **two-microphone time-difference-of-arrival** estimate:

- A sound from the side reaches the near mic slightly before the far mic. The
  delay is at most (mic spacing ÷ speed of sound), a fraction of a millisecond.
- The angle from straight ahead is `asin(delay × speed of sound ÷ spacing)`.
- The delay can only be measured in whole sample steps, so the angle can only
  take a few values, spaced like the arcsine of evenly spaced numbers. That is
  exactly the set above.

### 5.2 What it cannot tell

Two microphones give **one axis**. A sound 30° to the left in front and one
30° to the left behind arrive with the same delay, so they read the same
angle. Front and behind are mirror images and cannot be separated. Straight
ahead and straight behind both read about 0°.

So the HUD shows left, right, and **center**, meaning "ahead or behind you",
drawn as an arrow both up and down. It never claims front or behind.

### 5.3 How the hub turns tags into a side

`server/direction.py`, `DirectionTracker`:

1. **Pair each frame with the right tag.** Dara's snap test found the tag
   arrives **one frame ahead** of the audio it describes: the tag on the
   loudest frame is junk, the tag on the frame before it is the real
   estimate. Probably the glasses' speech enhancement delays the audio but not
   the tag. Each frame's loudness is paired with the previous frame's tag
   (`TAG_LEAD_FRAMES = 1`).
2. **Measure loudness the right way.** "Loudness" is the RMS of the
   sample-to-sample difference, a cheap high-pass, so the glasses' rumble does
   not count as loud.
3. **Keep 3 s of frames.** The direction is read when the classifier result
   lands, which for a cue is 1 to 2 s after the sound (2 windows at 0.5 s plus
   the round trip). A shorter window had already forgotten a snap by then.
4. **Let only the peak vote.** Take the frames at least half as loud as the
   loudest one in the window and use the **median** of their tags. A snap is
   1 to 3 frames far louder than the room, so only those vote; voting with the
   loudest half let 20 quiet room frames at -8/-17 outvote the snap. An alarm
   is loud for many frames, so its median has plenty to average.
5. **Map angle to side.** `SIGN = -1` (positive angles are the wearer's left,
   from the first live test). At or beyond **25°** is left or right; inside
   that is center.

### 5.4 Keeping the arrow steady

In `state.py`, a cue keeps the direction it started with for its whole 4 s,
so noise from elsewhere does not flip the arrow mid-cue. An alarm shows the
most common of its last 3 directions, so one stray reading does not flip it
but a real move does.

### 5.5 How well it works

Dara's snap test at 1 m (`docs/direction-test.md`): **left 4/5, right 4/5**
(8 of 10 on the correct side). Front read center 2/3. Behind read "right" 2/3:
behind is wrong more often than not, and nothing in software can fix that.
Quiet room reads -8/-17, which is center.

---

## 6. Drawing on the glasses

`plugin/src/hud.ts`:

- **One full-screen text container**, 576 × 288 px, updated with
  `textContainerUpgrade`. The G2 has one built-in proportional font, no size
  control, 4-bit green brightness (`textColor` 0 to 4).
- **At least 150 ms between writes**; only the newest pending content is
  written, older ones are dropped. The Bluetooth link cannot keep up with
  faster updates.
- **Centering** by padding with spaces, using estimated glyph widths (the
  firmware's real widths are not published; `?scale=` and `?line=` tune it).
- **Arrows**: `<-----  KNOCK`, `KNOCK  ----->`, and for center `^ | |` above
  the word and `| | v` below it, alarms included.
- **Tiers** (`plugin/src/settings.ts`), picked per sound on the phone page,
  saved on the phone:

  | Tier | Text | Flashing |
  |---|---|---|
  | Critical | `K N O C K` spaced capitals, between `=====` bars when there is no up/down arrow | every 0.3 s, full to faint, while shown |
  | Medium | `KNOCK` | every 0.7 s, full to half |
  | Normal | `knock`, dimmer | two blinks on arrival, then steady |

  Alarm and siren are locked to critical, drawn as plain `ALARM` / `SIREN`.
  "Bigger" is spacing and the frame, because there is no font size.
- **Sound menu on the glasses** (`plugin/src/menu.ts`). A tap opens it
  (long-press on the touchpad opens Even AI and never reaches the plugin)
  in the same text container: `All sounds`, one row per sound with its level,
  and `[ DONE ]`. Swipe up/down moves the cursor, tap cycles a sound off →
  normal → medium → critical → off, DONE (or a long-press, if it arrives) saves, double-tap
  closes without saving. Edits are a draft until saved. Alarm and siren are
  locked on. A sound set to off is dropped in the plugin (`render()` treats
  it as idle); the server does not know about the choices. An alarm arriving
  while the menu is open closes the menu, unsaved, and takes the display.
  Double-tap exits the app only when the menu is closed.

---

## 7. A doorbell, end to end

| t (s) | Where | What happens |
|---|---|---|
| 0.00 | Room | Doorbell rings 1 m to the wearer's right. |
| ~0.05 | Glasses | Mics capture it; firmware computes a direction tag; Bluetooth to the phone. |
| ~0.10 | Plugin | Base64-encodes the frame, sends it to the hub. |
| ~0.11 | Hub | Records loudness and tag in the direction tracker, forwards the frame to the iPhone. |
| ~0.12 | iPhone | High-pass filters the frame into the rolling buffer. |
| ≤0.5 | iPhone | Timer fires: gain-normalize the last 0.975 s, run YAMNet. "Doorbell 0.7". Send top 10 to the hub. |
| ~0.5 | Hub | Doorbell 0.7 ≥ 0.5: first hit, 1 of 3. Nothing shown yet. |
| ~1.0 | iPhone → hub | Next window, still ringing: second hit, 2 of 3. **Doorbell fires.** Direction tracker: peak frames read -37° → right. State becomes `cue / doorbell / right`. |
| ~1.1 | Hub → plugin | The 100 ms tick sees the change and sends the state frame. |
| ~1.2 | Plugin → glasses | Draws `DOORBELL  ----->` (medium tier), flashing every 0.7 s. |
| ~5.0 | Hub | 4 s cue ends; tick sends `idle`; the HUD goes blank. |

Dara's eval measured the classifier part at about 1.0 s to HUD for alarm,
siren, knock and horn, 2.5 s for dog, 3.2 s for doorbells (most ring twice;
the second ring completes 2 of 3). The phone, laptop and Bluetooth hops add
to that; end-to-end latency on the real glasses has not been filmed yet.

---

## 8. Known limits

- **One mic stream, speech-tuned.** The G2's processed audio buries alarms
  under rumble; the high-pass fixes alarms but hurts knocks and horns. Dual
  inference (filtered + raw) is measured to fix it and not yet shipped.
- **Front vs behind** cannot be sensed with one angle from two mics.
- **Doorbells vary.** Chimes read as "Bell"; old mechanical bells as
  "Telephone". Two-tone electronic doorbells detect reliably.
- **Most thresholds come from studio clips.** Only the smoke alarm was
  recorded through the G2. Real-glasses recordings of each class would tighten
  them.
- **The IPv6 address rotates.** The iPhone app has to be given the new address
  when it changes.
- **Four devices.** The plugin, laptop and iPhone all have to be up and on the
  same hotspot.

---

## 9. Where to change things

| To change | Edit | Then |
|---|---|---|
| Which YAMNet classes count, thresholds, k-of-n, cooldowns | `server/labels.py` | restart `main.py` |
| How long cues/alarms/speech stay up, priority | `server/state.py` | restart `main.py` |
| Left/right sign, center zone, direction voting | `server/direction.py` | restart `main.py` |
| High-pass cutoff, gain cap | `AudioClassificationHelper.swift` **and** `server/preprocess.py` (keep them equal) | rebuild the iOS app |
| Arrow drawing, tier styles, flashing | `plugin/src/hud.ts`, `plugin/src/settings.ts` | reload the plugin |
| Message formats | `PRD.md` first, then both ends | everyone |

Test without hardware, from `server/`:

```
python test_state.py
python fake_classifier.py --model ../audio_classification/ios/AudioClassification/TFLite/yamnet.tflite
python fake_glasses.py --wav ../plugin/recordings/alarm_1.wav --jsonl ../plugin/recordings/alarm_1.jsonl
python ../tools/eval.py --dual
```
