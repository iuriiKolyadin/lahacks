# Earshot — PRD and build plan

LA Hacks AI Hackathon 2026. Team: Dara, Iurii, Nikhil, Wendy.
Written Sat 2026-10-17 at 5:15 pm. **Deadline: Sun 12:00 pm.** About 18 hours.
Repo: https://github.com/iuriiKolyadin/lahacks. Working name "Earshot" (7 chars,
no "Even" in it, which Even's rules require).

Read sections 0 to 3, then your own section in 5. Everything else is reference.

---

## 0. The whole thing in five sentences

Earshot is an app for Even G2 smart glasses for deaf and hard-of-hearing people.
The glasses stay blank. When a sound they can't hear matters (doorbell, siren,
knock, alarm, someone saying their name), one line appears in their line of
sight saying what it was and, if we can, which way it came from. Even's built-in
Conversate mode already captions speech, so we never show words; we cover the
sounds Conversate ignores. Everything runs off the G2's own microphone; an
external mic is only for the direction arrow, and only if the glasses can't
give us direction themselves.

**The one rule:** by 11:00 pm tonight the full loop works once, end to end, on
the real glasses, with the G2 mic only and no arrow. Everything after that is
polish. Nobody starts a feature that isn't in section 2 "Must ship".

---

## 1. The demo (this is the product; build toward this script exactly)

Judge puts on the G2. Laptop sits on the table running the server. HUD is blank.

| Step | What a teammate does | What the judge sees on the glasses |
|---|---|---|
| 1 | Stands to the judge's left, says "hey, Alex" (the demo name) | `YOUR NAME` flashes, with `<-` if direction works |
| 2 | Plays a doorbell clip from a phone on the right | `doorbell  ->` for 4 s, then blank |
| 3 | Knocks hard on the table behind the judge | `knock` for 4 s, then blank |
| 4 | Plays a smoke-alarm clip | Whole screen: `ALARM` until it stops, then blank |
| 5 | Talks to the judge normally | `speech  <-` while they talk, fades 3 s after |
| 6 | Hands the glasses to the next judge | Nothing to configure |

Pitch, said once at the start: "A deaf person misses the doorbell, the siren,
and their own name. Conversate already captions what people say to you.
Earshot covers everything Conversate ignores, and shows nothing the rest of
the time."

Even's judges will ask three questions. Have the answers ready:
- Who uses this, and when? A deaf person at home or in an office, all day.
- Why G2? The cue has to be in your line of sight the instant the sound
  happens, hands free. A phone is too late. The G2 has no speaker, which costs
  a deaf user nothing.
- Can the judge try it right now? Yes, step 1 to 6 above, 60 seconds.

---

## 2. Scope

### Must ship (in this order; don't start the next until the previous works)

1. **Sound cue.** G2 mic audio goes to the laptop. YAMNet (Google's audio
   classifier) names the sound. If it's one of our classes, the HUD shows one
   line for 4 s. Classes: doorbell, knock, siren, alarm, car horn, dog bark.
2. **Alarm tier.** Siren or alarm takes the whole display at full brightness
   and suppresses everything else until it stops.
3. **Speech cue.** YAMNet says speech, and the SDK's `speakerRole` says it's
   not the wearer. Show `speech` while it continues. No words ever.
4. **Name flash.** Picovoice Porcupine keyword spotter catches the demo name.
   `YOUR NAME` at full brightness for 4 s.
5. **Blank by default.** Nothing on screen when nothing matters. Judges will
   watch for this; Even's brief is literally "stays in the background until
   it's useful."
6. **Beta build on a real G2.** Packaged `.ehpk`, pushed to a Beta group,
   installed, survives a 5-minute phone lock, double-tap exits.

### Should ship (only after 1 to 6 work, decided at the 11 pm checkpoint)

7. **Direction arrow.** `<-`, `->`, `(behind)` on every cue. Source is one of:
   the G2's own `direction` tag (free if the firmware fills it), or an ESP32
   with two mic modules on a cap. See section 6.
8. Companion phone page showing the event log, so a judge can scroll history.

### Won't ship (don't argue, don't start)

- Captions, transcription, translation, note-taking. Conversate does it, the
  SDK has no transcription API, Even says caption apps won't stand out.
- Anything medical, emergency-routing, or that calls anyone. Even Hub bans
  these outright and it would disqualify us from the Even prize.
- Camera, P4-EYE, QNX Pi, robot arm, Gemini summaries, ElevenLabs voice.

---

## 3. How it works

```
 G2 (4-mic array)                 iPhone (Even app runs our plugin)
   │ BLE: 16 kHz PCM               │
   │ + direction tag               │  WebSocket  ws://<LAPTOP_IP>:8000/ws/glasses
   │ + speakerRole                 ▼
   └──────────────────────▶  plugin (TypeScript, Wendy)
                              - forwards every audio event up
                              - renders whatever state comes down
                                   │ up:   {"pcm": base64, "direction": int|null, "speakerRole": "self|other|unknown"}
                                   │ down: {"state": "...", "label": "...", "dir": "...", "ttl_ms": N}
                                   ▼
                            laptop server (Python, Nikhil)
                              - YAMNet: sound class every 0.5 s
                              - Porcupine: name keyword
                              - urgency state machine
                              - direction from the tag, or from the ESP32 node
                                   ▲
                                   │ HTTP POST http://<LAPTOP_IP>:8000/direction
                            ESP32 + 2 mics on a cap (Arduino, Iurii) — phase 2 only
                              {"dir": "left|right", "margin_db": 8.2}
```

Three processes, three people, one contract each. Every node has a mock so
nobody waits on anybody:
- Server has `--mock`: cycles through every HUD state every 5 s with no audio.
  Wendy builds the whole plugin against this.
- Plugin has a `?demo=1` URL flag: cycles states locally with no server.
  Dara tests packaging and lifecycle against this.
- Server accepts a WAV file with `--wav doorbell.wav`: Nikhil tests the
  classifier with no glasses.

### 3a. The contracts (do not change these without telling everyone)

**Plugin to server, one JSON text frame per G2 audio event:**
```json
{"t": "audio", "pcm": "<base64 of the Uint8Array>", "direction": 1234, "speakerRole": "other", "ts": 1760745600123}
```
`pcm` is signed 16-bit little-endian, 16 kHz, mono, exactly as the SDK gives
it. `direction` is the raw int16 from the SDK or `null`. `ts` is `Date.now()`.

**Server to plugin, one JSON text frame whenever the state changes:**
```json
{"state": "cue", "label": "doorbell", "dir": "right", "ttl_ms": 4000, "level": 4}
```
- `state`: `idle` | `cue` | `speech` | `name` | `alarm`
- `label`: `doorbell` | `knock` | `siren` | `alarm` | `horn` | `dog` | `speech` | `name`
- `dir`: `left` | `right` | `front` | `behind` | `near` (near = unknown, no arrow)
- `ttl_ms`: how long to show before going blank; `0` means "until I say idle"
- `level`: text brightness 1 to 4

**ESP32 to server, HTTP POST, up to 10 per second:**
```json
{"dir": "left", "margin_db": 8.2}
```

**What the plugin renders per state (exact strings; one text container):**

| state | HUD text (centered by padding with spaces) | brightness | hold |
|---|---|---|---|
| idle | (empty string) | - | until next state |
| cue | `doorbell  ->` / `<-  knock` / `knock  (behind)` / `knock` | 4 | ttl_ms |
| speech | `speech  <-` | 2 | until idle, min 1 s |
| name | `<-  YOUR NAME` | 4 | ttl_ms |
| alarm | `ALARM` (or `SIREN`) on line 1, dir on line 2 | 4 | until idle |

---

## 4. What we have (confirmed 5:30 pm, nothing else)

| Item | Used for |
|---|---|
| Even G2 + Dara's iPhone with the Even app | the product |
| Laptops | server (Nikhil's), plugin dev (Wendy's), packaging (Dara's) |
| A second phone | hotspot, so the demo never touches venue Wi-Fi |
| Plain ESP32 dev board | phase 2 direction node, only if mic modules exist |
| Breadboard | same |
| ESP32-P4-EYE, QNX Pi, Linux Pi, UNO Q, 2 cameras, 2 brushless motors, arm parts | not used |

We have **no** microphone modules, sound sensors, or jumper wires. The only mic
in the plan is the one in the G2.

---

## 5. Who does what

Each person: install the tools listed, do the steps in order, tick the "done
when" test, then say so in the group chat. If stuck for 20 minutes, say so in
the chat; don't sit on it. Dara reassigns.

### 5.1 Wendy — glasses plugin and HUD

You own `plugin/`. You write the only code that runs on the phone and the
glasses. Background: this is a Vite + TypeScript web app; the Even app loads it
in a WebView and relays display and input to the glasses over Bluetooth.

**Tools to install (15 min)**
```bash
node -v                      # need 20 or newer
cd ~/Projects/lahacks
cp -r ~/Projects/lahacks-scratch/evenhub-templates/asr plugin   # Dara has this folder; or:
# npx degit even-realities/evenhub-templates/asr plugin
cd plugin
npm install
npm install @evenrealities/even_hub_sdk@0.0.16                  # the template pins 0.0.10; we need 0.0.16 for `direction`
```
Docs you will actually need, in order:
- Display API: https://hub.evenrealities.com/docs/build/display
- Device APIs (audio, events): https://hub.evenrealities.com/docs/build/device-apis
- Networking and whitelist: https://hub.evenrealities.com/docs/build/networking
- Background and lifecycle: https://hub.evenrealities.com/docs/build/background-lifecycle
- SDK README with the `direction` field: https://www.npmjs.com/package/@evenrealities/even_hub_sdk
- Optional: install Even's Claude Code plugin for live SDK help:
  `/plugin marketplace add even-realities/everything-evenhub` then
  `/plugin install everything-evenhub`

**Steps**
1. (5:30) `npm run dev`, then in another terminal
   `npx evenhub-simulator http://localhost:5173`. Confirm the template's
   "Listening…" text shows in the simulator.
2. (5:45) Edit `app.json`: `name` = `Earshot`, `package_id` =
   `com.earshot.lahacks` (lowercase, no hyphens), `min_sdk_version` =
   `0.0.16`, keep the `g2-microphone` permission, add:
   ```json
   { "name": "network", "desc": "Streams mic audio to the Earshot server.",
     "whitelist": ["http://LAPTOP_IP:8000", "ws://LAPTOP_IP:8000"] }
   ```
   Dara gives you `LAPTOP_IP` once the hotspot is up. It must be the exact
   origin, no wildcards.
3. (6:00) Replace `src/asr/stt.ts` with `src/link.ts`: open a WebSocket to
   `ws://LAPTOP_IP:8000/ws/glasses`, send one JSON frame per audio event in the
   section 3a format (base64-encode `audio.audioPcm`, include
   `audio.direction` and `audio.speakerRole`), and call `render(state)` on
   every message received. Reconnect with a 1 s backoff on close.
4. (6:30) Write `render(state)` in `src/hud.ts`: one full-screen text
   container, `isEventCapture: 1`, updated with `textContainerUpgrade` only.
   Map the section 3a table to strings. Use `textColor` for brightness
   (0.0.14+). Debounce writes to 150 ms. Pad with spaces to center; the font
   is fixed and not monospaced, so eyeball it on real glasses.
5. (7:00) Add `?demo=1`: if present, don't open the socket; cycle idle, cue,
   speech, name, alarm every 4 s so Dara can test packaging without a server.
6. (7:30) Lifecycle. On `SYSTEM_EXIT_EVENT` and `ABNORMAL_EXIT_EVENT`: call
   `audioControl(false)`, close the socket, unsubscribe. On double-tap: call
   `shutDownPageContainer(1)` (the system exit dialog; QA rejects apps that
   don't). On `visibilitychange` to visible: re-run `audioControl(true,
   AudioInputSource.Glasses)` and reconnect, because the mic stream and (on
   Android) the socket die when the phone locks.
7. (8:00) Test on real glasses with Dara: `npx evenhub qr --url
   http://LAPTOP_IP:5173` while the phone is on the hotspot. Then against
   Nikhil's server in `--mock` mode.

**Done when:** the server in `--mock` mode makes the real G2 show every row of
the section 3a table, the text is readable and centered, double-tap exits, and
after locking the phone for 5 minutes and reopening the app the states resume.

**If blocked:** the simulator ignores `textColor`; don't tune brightness there.
If the phone can't reach the laptop, it's the hotspot or the whitelist, not
your code; grab Dara.

### 5.2 Nikhil — audio server

You own `server/`. One Python process on your laptop. It receives audio from
the plugin, decides what's happening, and pushes a state back.

**Tools to install (20 min)**
```bash
python3 --version            # need 3.11 or 3.12; TensorFlow has no 3.13 wheel on some platforms
cd ~/Projects/lahacks && mkdir -p server && cd server
python3.12 -m venv .venv && source .venv/bin/activate
pip install fastapi "uvicorn[standard]" websockets numpy tensorflow pvporcupine
```
Model files, download now, commit to `server/models/`:
- YAMNet TFLite classifier and its class map:
  https://www.kaggle.com/models/google/yamnet/tfLite/classification-tflite
  (file `1.tflite`, rename `yamnet.tflite`; the class map CSV is inside the
  archive or at
  https://github.com/tensorflow/models/blob/master/research/audioset/yamnet/yamnet_class_map.csv)
- Porcupine: make a free account at https://console.picovoice.ai, create a
  custom keyword for the demo name (decide the name with Dara first), choose
  platform macOS, download the `.ppn`, put the access key in `server/.env` as
  `PICOVOICE_KEY=`. Don't commit the key.

**Steps**
1. (5:45) `main.py`: FastAPI app. `GET /` returns a status page. CORS wide
   open (`allow_origins=["*"]`, the Even WebView enforces CORS and the
   whitelist does not bypass it). `WebSocket /ws/glasses` accepts frames in
   the section 3a format, base64-decodes `pcm` into int16, appends to a
   rolling buffer, and sends state frames back on change. `POST /direction`
   accepts the ESP32 format and stores the latest value with a timestamp.
2. (6:15) `classify.py`: load `yamnet.tflite` with `tf.lite.Interpreter`.
   Every 0.5 s take the last 0.975 s (15600 samples) as float32 in [-1, 1],
   run it, take the top 3 classes. Map AudioSet names to ours:

   | YAMNet class name contains | our label |
   |---|---|
   | `Doorbell` | doorbell |
   | `Knock` | knock |
   | `Siren`, `Civil defense siren`, `Police car (siren)`, `Ambulance (siren)`, `Fire engine, fire truck (siren)` | siren |
   | `Smoke detector, smoke alarm`, `Fire alarm`, `Alarm` | alarm |
   | `Vehicle horn, car horn, honking` | horn |
   | `Dog`, `Bark` | dog |
   | `Speech`, `Conversation`, `Narration, monologue` | speech |

   Threshold 0.3 for cue classes, 0.5 for speech. Log every top-3 with scores
   so we can tune at the table.
3. (6:45) `--wav path.wav` flag: feed a 16 kHz mono WAV through the same
   buffer at real-time pace and print the labels. Test with the clips in
   section 7. This is your unit test; get doorbell and siren right before
   touching anything else.
4. (7:15) `state.py`: the urgency state machine, pure function of (events,
   now). Rules: alarm or siren beats everything and holds until 2 s after the
   last detection. Otherwise a cue holds 4 s and a newer cue replaces it.
   Speech only if `speakerRole != "self"`, shows while detected, fades 3 s
   after. Name beats speech and cue. Emit a state frame only on change.
5. (7:45) `--mock` flag: no audio; cycle idle, cue(doorbell,right),
   speech(left), name(left), alarm(siren,behind) every 5 s. Wendy needs
   this by 7 pm at the latest, so do step 5 before step 4 if you're behind.
6. (8:30) `name.py`: Porcupine. Feed it the same int16 stream in 512-sample
   frames. On detect, emit a `name` event.
7. (9:00) Direction: if the plugin's `direction` field is non-null and Dara's
   test says it tracks position, map it to left/right/front/behind using the
   thresholds from that test. Else if `/direction` has a value under 1 s old,
   use it. Else `near`.
8. (9:30) Live test with Wendy's plugin on the real glasses. Tune
   thresholds in the hall noise.

**Done when:** with the real glasses connected, a phone-played doorbell
produces `cue/doorbell` within 1 s, a siren clip produces `alarm` and holds, a
knock produces `cue/knock`, saying the name produces `name`, and 30 s of
hallway noise produces nothing.

**If blocked:** if TensorFlow won't install, `pip install ai-edge-litert`
gives the same `Interpreter`. If YAMNet misses knocks on the G2 stream (the
stream is speech-processed), try `AudioInputSource.Phone` in the plugin
first; it's one line. If Porcupine fights you past 9:30, cut the name feature
and tell Dara.

### 5.3 Iurii — direction, hardware, and the physical demo

You own everything physical: the direction arrow (phase 2), the demo rig, and
the sound clips. Phase 2 only starts if phase 1 isn't blocked on anything.

**Tools to install (15 min, only if the ESP32 node happens)**
- Arduino IDE 2.x, then Boards Manager: install "esp32 by Espressif Systems".
- Libraries: none needed for HTTP POST (`WiFi.h` and `HTTPClient.h` ship
  with the core). For I2S mics: `driver/i2s.h` ships with the core too.

**Steps**
1. (5:30, first, with Dara) **The direction test.** This decides phase 2.
   Dara runs the plugin on the real glasses with a console log of
   `audio.direction`. You stand 1 m away and talk for 5 s from the left,
   right, front, behind, and record the numbers for each. Write them in
   `docs/direction-test.md`. Verdict: either the numbers separate by
   position (Tier 0 works, no hardware needed, hand the thresholds to
   Nikhil) or they're always `null` or noise (go to step 2).
2. (6:00) **Mic modules.** Go to the MLH hardware table, if there is one. Ask
   for, in order: two I2S mic modules (INMP441, SPH0645, ICS-43434); or two
   analog mic/sound modules (KY-038, KY-037, MAX4466); plus ten male-to-female
   jumper wires and a USB cable that fits the ESP32 (data, not charge-only).
   No mics means no ESP32 node; skip to step 5 and the arrow ships only if
   Tier 0 worked.
3. (6:30) **Wire it.** Two mics 15 cm apart on a strip of cardboard that sits
   on a cap, one over each ear. I2S: SCK, WS, SD to the ESP32 I2S pins, both
   mics on the same bus with L/R select tied opposite. Analog: each mic's
   analog out to an ADC pin (GPIO 34, 35), 3.3 V and GND.
4. (7:30) **Firmware.** Every 100 ms: read 100 ms of samples from each mic,
   compute RMS of each, `margin_db = 20*log10(rms_left/rms_right)`. If
   `abs(margin_db) > 6`, POST `{"dir":"left"|"right","margin_db":x}` to
   `http://LAPTOP_IP:8000/direction`. Join the hotspot SSID in `setup()`.
   Blink the onboard LED on every POST so you can see it alive.
5. (8:00) **Demo rig.** Download the clips in section 7 to a phone. Borrow or
   buy a Bluetooth speaker; a phone speaker is too quiet in the hall. Tape
   L and R labels on the table. Find a cap for the mic strip if it exists.
6. (8:30) **Bench test** with Nikhil's server log open: talk from left
   and right; the log must show the right side 9 times out of 10 at 1 m.
   Record the number in `docs/direction-test.md`; it's our pitch number.
7. (9:00) **Cutoff.** If left/right isn't working, stop, unplug it, and go
   help Nikhil tune thresholds. The product is unchanged without it.

**Done when:** either `docs/direction-test.md` says Tier 0 works with
thresholds, or the ESP32 POSTs the correct side 9 of 10 times, or it says
"no direction, cut at 9 pm" and everyone knows.

### 5.4 Dara — integration, glasses, submission

You own the G2, the phone, the hotspot, the Beta build, the Devpost page, the
video, and the clock. You are the only person who touches the Even developer
portal.

**Tools (10 min)**
- Even app on the iPhone, 2.2.10 or newer, signed in, developer access enabled
  at https://evenhub.evenrealities.com (then fully quit and reopen the phone
  app; people miss this). Auto-lock on the phone set to Never for the demo.
- `npm i -g @evenrealities/evenhub-cli` on your laptop for `evenhub pack`
  and `evenhub qr`.
- Devpost project created at https://la-ai-hackathon-2026.devpost.com, all
  four added, challenges selected: Even Realities, Beyond the Digital, Applied
  Intelligence.

**Steps**
1. (5:20) Hotspot up on the second phone. Nikhil's laptop and your iPhone
   join it. Write the laptop's IP in the group chat and in `README.md` as
   `LAPTOP_IP`. Hotspots usually hand out the same IP again; if it changes,
   Wendy's whitelist has to be rebuilt, so don't toggle it.
2. (5:30) Pair the G2, update firmware, run Wendy's step 1 template on the
   real glasses with `npx evenhub qr --url http://LAPTOP_IP:5173`. One tap
   event must show in the console. Then do Iurii's step 1 direction test with
   him. While you're at it, dump 30 s of PCM to a WAV while Iurii plays a
   doorbell and a siren, and give the WAV to Nikhil; it tells him what the
   G2 stream really sounds like.
3. (6:00) Go to the Even table (closes 8 pm). Ask: does the `direction` field
   in `AudioEvent` work on current firmware, and what is its unit? Confirm
   the Beta group flow. Ask whether "sound awareness for deaf users" is
   considered medical (it isn't, but hear them say it).
4. (6:30) Decide the demo name with the team (a teammate's first name, two
   syllables, easy to say). Tell Nikhil so he trains the Porcupine keyword.
5. (7:00) Devpost page skeleton: title, one-line, the section 1 demo table
   turned into prose, "Built with" list. Leave the video for the morning.
6. (8:00) First pack. With Wendy's `?demo=1` build:
   `npm run build && evenhub pack app.json dist -o earshot.ehpk`. Fix whatever
   the packer rejects now, not at 8 am. Then: developer portal, create a
   Beta group containing your own account email, upload under Builds, push to
   the group, on the phone go to Me, then Beta tester, install. This shakes
   out the whole submission path with a throwaway build.
7. (9:30) Integration. Everyone's pieces on the real glasses, run the section
   1 script start to finish. Film it on your phone even if it's rough; that's
   the backup video.
8. (11:00) **Checkpoint.** Full loop worked once, or cut: name first, then
   direction, then speech cue. Announce the cut in the chat.
9. (12:30 am) Lock test: phone locked 5 min, reopen, states resume. Denied
   mic permission shows something sane. Double-tap exits.
10. (8:00 am) Final pack and Beta push with the real build. Install, test the
    script once more. Record the 2 to 3 minute video: 20 s pitch, the six demo
    steps, 20 s of how it works with the architecture diagram.
11. (10:00 am) Five rehearsals with someone who hasn't worn the glasses.
    README section "Installing and running on G2" written (Even requires it).
12. (11:00 am) Submit Devpost and confirm the Beta build is the final one.
    Nobody touches code after this.

**Done when:** the Devpost page and the Even Beta build are both submitted by
11:30 am and the demo has been run five times in a row without touching a
laptop.

---

## 6. Direction: the three tiers, in order

The arrow is phase 2. Phase 1 ships with `dir: near` (no arrow) and is a
complete product.

| Tier | How | Costs | Decided by |
|---|---|---|---|
| 0 | The G2's own `direction` field on every audio event (signed int16, undocumented unit, may be null on current firmware) | 10 min test | Iurii + Dara, 5:30 pm |
| B | ESP32 + two mic modules on a cap, left/right from level difference, POST to the server | mic modules from the MLH table, Iurii's evening | 9:00 pm cutoff |
| C | No arrow | nothing | automatic |

A single microphone, including the G2's, can never give direction on its own.
That's the only reason any other hardware is in this document.

---

## 7. Things to get and download tonight

**Sound clips, downloaded to a phone, not streamed at the table**
- [ ] doorbell, two-tone, 3 s
- [ ] knock on a door, 2 s
- [ ] smoke alarm beep, 5 s
- [ ] police siren, 5 s
- [ ] car horn, 2 s
- [ ] dog bark, 2 s
- [ ] 30 s of hallway crowd noise, for threshold tuning
Also save each as a 16 kHz mono WAV in `server/clips/` for Nikhil's
`--wav` test (`ffmpeg -i in.mp3 -ar 16000 -ac 1 out.wav`; ffmpeg is on
Dara's Mac).

**Physical**
- [ ] A Bluetooth speaker, or the loudest phone we have
- [ ] Tape and a marker for L / R labels
- [ ] Laptop chargers, everyone's
- [ ] A cap, only if the ESP32 mic node happens
- [ ] From the MLH table, only if it exists: 2 mic modules, 10 jumper wires,
      a data USB cable for the ESP32

**Accounts and keys**
- [ ] Even developer access on Dara's account (done before 6 pm)
- [ ] Picovoice account and the demo-name `.ppn` (Nikhil, by 8:30 pm)
- [ ] Devpost project with all four members (Dara, by 7 pm)

---

## 8. Timeline

| Time | Must be true |
|---|---|
| 5:30 pm | Template renders on the real G2. Direction test done, verdict written. |
| 6:00 pm | Hotspot up, `LAPTOP_IP` known. Everyone's tools installed. |
| 7:00 pm | Server `--mock` works. Plugin renders mock states in the simulator. YAMNet labels a doorbell WAV. |
| 8:00 pm | Even table closes. First `.ehpk` packed and installed from Beta. Plugin renders mock states on real glasses. |
| 9:00 pm | Live audio from the G2 reaches the server; YAMNet runs on it. ESP32 cutoff. |
| 11:00 pm | **Full loop on real glasses once.** Cut list decided. |
| 12:30 am | Lock test, exit test, permission-denied test pass. |
| 2:00 am | Thresholds tuned in hall noise. Everyone sleeps except whoever volunteers for polish. |
| 8:00 am | Final pack, Beta push, video recorded. |
| 10:00 am | Five rehearsals. README done. |
| 11:00 am | Submitted. Code frozen. |
| 12:00 pm | Deadline. Judging follows; glasses charged, laptop plugged in, speaker charged. |

---

## 9. Risks and what we do about each

| Risk | How we'll know | What we do |
|---|---|---|
| G2 audio is speech-filtered and drops doorbells or knocks | Dara's 5:30 WAV; Nikhil's `--wav` test | Switch the plugin to `AudioInputSource.Phone` (one line). If still bad, laptop mic feeds YAMNet and the glasses only display. |
| `direction` is always null | 5:30 test | Tier B or no arrow. Product unchanged. |
| Phone can't reach the laptop | 5:30 | It's the hotspot or the whitelist. Both phones and the laptop on the same hotspot; whitelist is the exact `http://IP:8000` and `ws://IP:8000`. |
| Mic stream dies on phone lock | 12:30 am test | Re-call `audioControl(true)` and reconnect on `visibilitychange`. Already in Wendy's step 6. |
| Packer rejects the manifest | 8 pm throwaway pack | That's why we pack at 8 pm, not 8 am. |
| Venue noise triggers false cues | 2 am tuning | Raise thresholds, require two consecutive windows, demo with clean clips on a speaker. |
| Porcupine misses the name | 9:30 pm | Lower sensitivity, say the name twice in the demo, or cut it. |
| YAMNet thinks hall chatter is "speech" constantly | 9:30 pm | Speech threshold 0.5 and `speakerRole != self`; if still noisy, cut the speech cue. |
| No mic modules at the MLH table | 6 pm | No ESP32 node. Iurii moves to demo rig and tuning. |

---

## 10. Submission checklist (Sunday 11:00 am)

- [ ] Devpost: description, track = Beyond the Digital, challenges = Even
      Realities and Applied Intelligence, public repo link, 2 to 3 min video,
      "Built with" list, all four members.
- [ ] Even: `.ehpk` on a Beta group, installed on Dara's phone, Even Hub app
      name written on the Devpost page, README has an "Install and run on G2"
      section listing any keys needed (Picovoice).
- [ ] Repo public, README with: what it is, the demo script, architecture,
      how to run each of the three nodes, the contracts from section 3a.
- [ ] Glasses charged. Phone charged, auto-lock off. Laptop plugged in.
      Speaker charged. Clips on the phone.
- [ ] One number for the pitch, measured: sound-to-HUD latency for a doorbell
      (film glasses and speaker together, count frames), and direction
      accuracy if we have it.

---

## 11. Prior art, for the Devpost page

- SoundSense (Reality Hack 2026, Best Edge AI Hardware): sound-sensor array on
  an Arduino UNO Q, captions plus direction on a headset. We keep the
  direction idea and drop captions.
- Synesthesia (HackGT 13, Shipyard 1st): mic array plus YAMNet, siren and knock
  shown with direction on a phone.
- Here (Knight Hacks IX): mic array, urgency tiers deciding what interrupts.
- None of them ran on display-only glasses. Nothing on Even Hub does this.
