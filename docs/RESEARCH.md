# Research: what Even Realities has, what the SDK gives us, prior art, and what Cue adds

Compiled Sat 2026-10-17 between 3 pm and 5 pm from the Even docs, the npm SDK
package, the Even GitHub org, the community app list, Devpost, and the LA Hacks
challenge page. Facts marked "verified" were read directly from the source
named. Everything else is from secondary sources and says so.

## 1. What Even Realities has

### The hardware (verified: hub.evenrealities.com/docs/get-started/overview)
- Even G2 glasses: dual micro-LED display, 576 x 288 px per eye, monochrome
  green with 16 brightness levels. A 4-microphone array. Touchpads on both
  temples. Optional R1 ring. An IMU.
- No camera. No speaker. The company markets this as privacy by design.
- Pairs to the phone over Bluetooth LE 5.2. The phone runs the apps; the
  glasses only render output and capture input.

### Built-in features in the Even app (secondary: App Store listing, reviews)
- Conversate: live captions of speech, meeting summaries. This is the
  built-in answer to "captions for deaf users."
- Even AI: a voice assistant.
- Notification mirroring from the phone, navigation, teleprompter, dashboards.
- Marketing copy promises "AI-powered voice isolation" and "directional
  microphones [that] focus on speech." This matters for us: the audio we get
  is probably speech-enhanced.

### Even Hub, the app platform (verified: docs overview, networking, packaging)
- Third-party apps are "plugins": ordinary web apps (HTML, CSS, JS or TS; any
  stack such as Vite or React). The Even app loads them in a WebView on the
  phone and relays display and input to the glasses.
- Workflow: build with Vite; preview with `evenhub-simulator`; sideload on a
  real G2 via QR with `evenhub qr --url`; package with
  `evenhub pack app.json dist -o app.ehpk`; upload to the developer portal;
  push to a Beta group; install from the phone's Me → Beta tester.
- Packages: `@evenrealities/even_hub_sdk` (0.0.16 as of today),
  `@evenrealities/evenhub-cli` (0.1.14), `@evenrealities/evenhub-simulator` (0.9.5).
- Even publishes four starter templates (minimal, image, text-heavy, asr) at
  github.com/even-realities/evenhub-templates, pinned to SDK 0.0.10, and a
  Claude Code plugin with 12 skills at
  github.com/even-realities/everything-evenhub.

### The community (verified: github.com/pangoleen/awesome-even-realities-g2, ~200 apps)
Crowded categories: readers and teleprompters (~30), transit and navigation
HUDs (~30), dashboards (~20), speech-to-text and captions (~8, e.g. G2 Captions,
Convo Exchange, soniox-translate), agent terminals on the glasses (~15).

Closest existing apps to ours, none of which does what we do:
- Applied Resonance: learns a machine's healthy sound through the G2 mic and
  warns on change. Audio classification, industrial, no direction.
- Birdie: identifies bird calls from the G2 mic.
- MuSe: identifies songs playing nearby.
- EvenAware: aggregates phone notifications onto the lens. No audio sensing.
- ExEye: pairs an ESP32 camera with the G2 for vision questions.

Nothing on Even Hub or in the community list detects non-speech sounds for
deaf users, puts a direction on a sound, or decides what is urgent enough to
interrupt. Only one Even G2 project exists on Devpost at all (LinguaLens, an
English coach), and it won nothing.

### The LA Hacks challenge (verified: evenrealities-lahacks.vercel.app and /starterpack)
- Brief: build an Even Hub app around "Quiet Tech", technology that stays in
  the background until it's useful, "a small, timely cue in the wearer's line
  of sight."
- Judging: Made for G2, Originality, User Experience, Technical Execution.
  Judges walk up and ask: who uses this and when, why G2, can I try it now.
- Prizes: 1st, a G2 for every team member; 2nd, $250 OpenAI credit each;
  3rd, $100 each.
- Hard rules: `.ehpk` on a Beta group and running on a physical G2 at judging;
  public repo; 2 to 3 minute video; README with install steps. App name 20
  characters or fewer, not containing "Even". **"Even Hub doesn't allow
  medical, financial, or emergency-routing apps."** Health apps: "keep it to
  wellness, with no medical advice."
- "We see a lot of teleprompters, translators, and note-takers. They're
  useful, but they won't stand out."
- Suggested directions: games that react to you, chord charts, recipe or
  repair steps while hands are busy, workout form cues, lab protocols,
  travel cues.
- Schedule: loaner applications closed Sat noon; Even table open Sat 4 to 8 pm
  and Sun from 9 am; deadline Sun 12 pm.

## 2. What the SDK gives us (verified: SDK 0.0.16 `index.d.ts` and README, plus the docs pages named)

### Audio
- `bridge.audioControl(true, AudioInputSource.Glasses)` starts the glasses
  mic; `audioControl(false)` stops it. `AudioInputSource.Phone` uses the
  phone mic instead and needs no startup page.
- Audio arrives in `bridge.onEvenHubEvent(e => e.audioEvent)` as
  `audioPcm: Uint8Array`, PCM 16 kHz, signed 16-bit little-endian, mono.
  Continuous frames; no documented voice-activity gating.
- `AudioEvent.direction: number | null`: "Raw glasses direction tag for
  this PCM frame, or null when unavailable." README: "a signed int16 ... the
  SDK does not convert its unit or range." Null on the phone mic and on older
  hosts. Added in 0.0.14. Nobody outside Even has documented its range, no
  community app uses it, and the Even FAQ still lists direction reporting as
  "on the roadmap." Whether current firmware fills it in is unknown until we
  test it.
- `AudioEvent.speakerRole: "self" | "other" | "unknown"`: the app-side
  algorithm's guess whether the frame is the wearer speaking. Not a firmware
  identity assertion.
- The SDK calls the stream "processed PCM" (the Chinese comment says 处理后,
  "after processing"). Combined with the marketing claim of voice isolation,
  expect doorbells and sirens to come through attenuated and knocks to be the
  risk. Community apps classify music (MuSe), birdsong (Birdie), and machine
  sounds (Applied Resonance) from this stream, so non-speech does get through.
- There is no transcription or speech-recognition API. The `asr` template's
  STT provider is a placeholder that throws.
- Permissions: `g2-microphone` for the glasses mic, `phone-microphone` for
  the phone mic.

### Display (verified: docs/build/display)
- 576 x 288 canvas per eye, origin top-left, 4-bit grey rendered as green.
- Per page: up to 4 image containers and 8 other containers. Exactly one
  container has `isEventCapture: 1` and receives all input.
- Text containers: create with `createStartUpPageContainer`, update with
  `textContainerUpgrade` (preferred; no flicker). `textColor` 0 to 4 sets
  brightness (SDK 0.0.14+). One built-in LVGL font; no size, weight, or family
  control; not monospaced; center by padding with spaces. A full-screen
  container holds roughly 400 to 500 characters.
- Images: up to 288 x 144, 4-bit; each `updateImageRawData` holds the path
  for 100 ms. A community sheet-music app reported about 3 s bitmap latency on
  the G1; use text, not images, for anything time-sensitive.

### Input (verified: docs/build/device-apis)
- `CLICK_EVENT` (0), `SCROLL_TOP_EVENT` (1), `SCROLL_BOTTOM_EVENT` (2),
  `DOUBLE_CLICK_EVENT` (3), `LONG_PRESS_EVENT` (9), `LONG_PRESS_RELEASE_EVENT` (10).
- `CLICK_EVENT` is 0 and protobuf omits zero fields, so a tap can arrive with
  `eventType === undefined`; resolve the default inside the envelope check.
- Double-tap on the root page must call `shutDownPageContainer(1)` to open
  the system exit dialog; QA rejects apps that don't.
- IMU: `imuControl(true, ImuReportPace.P500)`; samples on
  `sysEvent.imuData.{x,y,z}` when `eventType === IMU_DATA_REPORT`.

### Networking (verified: docs/build/networking)
- fetch, XHR, and WebSocket are allowed only to origins listed in `app.json`
  under `permissions[{name:"network", whitelist:[...]}]`. Exact origins, no
  wildcards, no bare hosts. Plain `http://` is tolerated for a LAN dev server.
- The whitelist does not bypass CORS. The server must send
  `Access-Control-Allow-Origin` and handle OPTIONS preflight if needed.
- The phone must reach the laptop by LAN IP. Venue Wi-Fi client isolation can
  block this; the starter pack says bring a hotspot.

### Lifecycle (verified: docs/build/background-lifecycle)
- iOS keeps the WebView and JS state alive in the background; Android may
  reclaim it under memory pressure.
- The mic stream stops when the WebView suspends. Re-enable on foreground.
- WebSockets usually survive on iOS and usually drop on Android; reconnect on
  close.
- `localStorage` always survives. The Beta QA test locks the phone 5 minutes
  and relaunches.

### Packaging (verified: docs/ship/packaging)
- `app.json` needs `package_id` (reverse domain, lowercase, no hyphens),
  `edition: "202601"`, `name` (20 chars max), `version`, `min_sdk_version`,
  `entrypoint`, `permissions`, `supported_languages`.
- `evenhub pack app.json dist -o app.ehpk`. Declare only permissions you use;
  unused ones are flagged at review. Never bundle secrets; released packages
  can be extracted.

## 3. Prior art (Devpost and hackathon showcases, Oct 2026)

Sound awareness for deaf users has won at three separate 2026 hackathons, on
phones or headsets, never on display-only glasses:
- SoundSense, Reality Hack @ MIT 2026, Best Use of Edge AI for Hardware
  (Qualcomm): KY-037 sound-sensor array on an Arduino UNO Q, whisper.cpp
  captions, direction of loudest sensor, shown on a headset. Notes the sensors
  "output only binary (noise or no noise)."
  https://devpost.com/software/soundsense-tfqiv9
- Synesthesia, HackGT 13, The Shipyard 1st: Pi Pico mic array, YAMNet on
  TFLite, siren shown red/blue on the side it came from, knock pulses in front.
  https://devpost.com/software/synesthesia-b1p9r3
- Here, Knight Hacks IX, Hugging Face prize: ReSpeaker mic array plus camera
  plus haptic belt; captions over the speaker; an urgency layer decides
  whether a sound is ambient, notice, important, or urgent; "a fan doesn't
  buzz you, a car behind you always does."
  https://devpost.com/software/here-vqlrhg
- C-HUD Vision, HackGT 13: four mics on a cap with an ESP32, YAMNet names the
  sound, urgency tiers, alarms take the whole screen.
  https://devpost.com/software/chud
- Graption and Voice-over: captions anchored to the speaker, plus a pop-up
  when the deaf user is addressed by name.

What judges rewarded across ~700 hardware and XR winners we scanned:
- A live 30-second demo the judge does themselves, described in the first
  sentence of the writeup.
- A named user and a visible sensor rig. Pure-software "glasses" mockups only
  won niche sponsor prizes.
- A HUD that shows almost nothing most of the time; "intervene or stay quiet"
  as the core decision.
- One measured number ("passed at 0.32 m", "51 fps at 3.2 W").
- Glasses as output, something else as sensor. HackMIT 2025's Mentra track
  winner paired camera glasses with Even G1 display glasses; judges rewarded
  the split.

Things that have already been done on glasses and would not read as new:
face memory for dementia (Forget Me Not, Lumos, Dementia Assist, MemoLens),
AR CPR guidance (Pulse at LA Hacks 2025, Proximity Pulse), captions
(everything).

## 4. What Cue adds

| Even already has | Cue adds |
|---|---|
| Conversate: captions of speech | Captions too, but as the lowest-priority state and under an arrow to the side the speaker is on, which Conversate does not show. Any sound cue replaces them. |
| A 4-mic array with a `direction` tag the SDK exposes but no app uses | The first app to use it, if the firmware fills it in; a two-mic fallback if not. |
| Raw PCM to plugins, no classifier | YAMNet on the laptop naming doorbell, knock, siren, alarm, horn, dog. |
| `speakerRole` self/other | A speech cue that ignores the wearer's own voice. |
| A display that most apps keep full of text | A display that is blank until one of seven things happens. Even's own brief, taken literally. |
| No app for deaf users beyond captions | The sounds Conversate ignores, for the one group for whom the G2's missing speaker costs nothing. |

Why this and not the other ideas we researched: the assembly coach, rear
awareness, and face memory all need a camera we don't have on the glasses and
hours of P4-EYE Wi-Fi bring-up; the CPR coach and EMT tools are banned by Even
Hub's medical rule; the caption-style apps are the ones Even says won't stand
out. Sound awareness needs only the G2 mic for the whole product, has three
recent winning precedents on other hardware, and is empty on this hardware.
