# Earshot — build plan

How, who, when. The what and why are in `PRD.md`. Read sections 1 and 2, then
your own part of section 3.

## 1. Architecture

Three processes, three owners, one contract between each pair.

```
 G2 (4-mic array)            iPhone: Even app running our plugin
   │ BLE: 16 kHz PCM          │
   │ + direction tag          │ WebSocket  ws://LAPTOP_IP:8000/ws/glasses
   │ + speakerRole            ▼
   └─────────────────▶  plugin  (TypeScript, Wendy)
                        - sends every audio event up
                        - renders whatever state comes down
                              │
                              ▼
                        server  (Python, Nikhil)
                        - YAMNet: sound class every 0.5 s
                        - Porcupine: name keyword
                        - urgency state machine
                        - direction: G2 tag, or the ESP32 node
                              ▲
                              │ HTTP POST http://LAPTOP_IP:8000/direction
                        ESP32 + 2 mics on a cap  (Arduino, Iurii) — phase 2 only
```

Every node has a stand-in so nobody waits:
- `server --mock` cycles through every HUD state every 5 s with no audio.
- `plugin ?demo=1` cycles states locally with no server.
- `server --wav file.wav` feeds a clip through the classifier with no glasses.

## 2. Contracts (change these only in the group chat, with everyone's ok)

**Plugin to server, one JSON text frame per G2 audio event**
```json
{"t":"audio","pcm":"<base64 of audioPcm>","direction":1234,"speakerRole":"other","ts":1760745600123}
```
`pcm` is int16 little-endian, 16 kHz, mono, untouched from the SDK.
`direction` is the SDK's raw int16 or `null`. `ts` is `Date.now()`.

**Server to plugin, one JSON frame on every state change**
```json
{"state":"cue","label":"doorbell","dir":"right","ttl_ms":4000,"level":4}
```
- `state`: `idle` | `cue` | `speech` | `name` | `alarm`
- `label`: `doorbell` | `knock` | `siren` | `alarm` | `horn` | `dog` | `speech` | `name`
- `dir`: `left` | `right` | `front` | `behind` | `near` (near = no arrow)
- `ttl_ms`: show for this long then blank; `0` = until the next frame
- `level`: brightness 1 to 4

**ESP32 to server, HTTP POST, up to 10 per second**
```json
{"dir":"left","margin_db":8.2}
```

**HUD rendering, one text container, exact strings**

| state | text | brightness | hold |
|---|---|---|---|
| idle | `` (empty) | - | until next |
| cue | `doorbell  ->`, `<-  knock`, `knock  (behind)`, `knock` | 4 | ttl_ms |
| speech | `speech  <-` | 2 | until idle, at least 1 s |
| name | `<-  YOUR NAME` | 4 | ttl_ms |
| alarm | line 1 `ALARM` or `SIREN`, line 2 direction | 4 | until idle |

## 3. Who does what

Rules: install your tools, do your steps in order, run your "done when" test,
say so in the chat. Stuck 20 minutes: say so in the chat. Dara reassigns.

### 3.1 Wendy — plugin (`plugin/`)

The only code that runs on the phone and the glasses. A Vite + TypeScript web
app; the Even app loads it in a WebView and relays display and input to the
glasses over Bluetooth.

Install:
```bash
node -v                                   # 20+
cd ~/Projects/lahacks && npx degit even-realities/evenhub-templates/asr plugin
cd plugin && npm install
npm install @evenrealities/even_hub_sdk@0.0.16   # template pins 0.0.10; 0.0.16 adds `direction`
```
Docs, in the order you'll need them:
display https://hub.evenrealities.com/docs/build/display ·
device APIs https://hub.evenrealities.com/docs/build/device-apis ·
networking https://hub.evenrealities.com/docs/build/networking ·
lifecycle https://hub.evenrealities.com/docs/build/background-lifecycle ·
SDK README (the `direction` field) https://www.npmjs.com/package/@evenrealities/even_hub_sdk

Steps:
1. `npm run dev` and `npx evenhub-simulator http://localhost:5173`. The
   template's "Listening…" shows in the simulator.
2. `app.json`: `name` Earshot, `package_id` `com.earshot.lahacks`,
   `min_sdk_version` `0.0.16`, keep `g2-microphone`, add
   `{"name":"network","desc":"Streams mic audio to the Earshot server.","whitelist":["http://LAPTOP_IP:8000","ws://LAPTOP_IP:8000"]}`.
   Exact origins, no wildcards. Dara gives you LAPTOP_IP.
3. Replace `src/asr/stt.ts` with `src/link.ts`: WebSocket to
   `ws://LAPTOP_IP:8000/ws/glasses`, one frame per audio event in the section 2
   format, `render(state)` on every message, reconnect with 1 s backoff.
4. `src/hud.ts`: one full-screen text container with `isEventCapture: 1`,
   updated only with `textContainerUpgrade`, `textColor` for brightness,
   150 ms debounce, strings from the section 2 table, centered by padding.
5. `?demo=1`: skip the socket, cycle idle, cue, speech, name, alarm every 4 s.
6. Lifecycle: on `SYSTEM_EXIT_EVENT` / `ABNORMAL_EXIT_EVENT` stop audio, close
   socket, unsubscribe. Double-tap calls `shutDownPageContainer(1)`. On
   `visibilitychange` to visible, re-call `audioControl(true,
   AudioInputSource.Glasses)` and reconnect, because the mic stream dies when
   the phone locks.
7. Real glasses with Dara: `npx evenhub qr --url http://LAPTOP_IP:5173`, then
   against Nikhil's `--mock` server.

Done when: the mock server makes the real G2 show every row of the HUD table,
readable and centered; double-tap exits; after a 5-minute phone lock the
states resume.

### 3.2 Nikhil — server (`server/`)

One Python process on your laptop. Receives audio, decides what's happening,
pushes a state.

Install:
```bash
python3 --version                         # 3.11 or 3.12 (TensorFlow has no 3.13 wheel on some platforms)
cd ~/Projects/lahacks && mkdir -p server/models server/clips && cd server
python3.12 -m venv .venv && source .venv/bin/activate
pip install fastapi "uvicorn[standard]" websockets numpy tensorflow pvporcupine
```
Models, download now into `server/models/`:
- YAMNet TFLite + class map: https://www.kaggle.com/models/google/yamnet/tfLite/classification-tflite
  (class map also at https://github.com/tensorflow/models/blob/master/research/audioset/yamnet/yamnet_class_map.csv)
- Porcupine: free account at https://console.picovoice.ai, custom keyword =
  the demo name, platform macOS, download the `.ppn`. Access key goes in
  `server/.env` as `PICOVOICE_KEY=`. Never commit the key.

Steps:
1. `main.py`: FastAPI. CORS `allow_origins=["*"]` (the Even WebView enforces
   CORS; the whitelist does not bypass it). `WebSocket /ws/glasses` takes the
   section 2 frames, decodes `pcm` to int16 into a rolling buffer, sends state
   frames back on change. `POST /direction` stores the latest value with a
   timestamp. `GET /` is a status page.
2. `classify.py`: `tf.lite.Interpreter` on `yamnet.tflite`. Every 0.5 s run
   the last 15600 samples as float32 in [-1, 1]. Top 3 classes. Map:

   | YAMNet class contains | ours |
   |---|---|
   | Doorbell | doorbell |
   | Knock | knock |
   | Siren, Civil defense siren, Police car (siren), Ambulance (siren), Fire engine, fire truck (siren) | siren |
   | Smoke detector, smoke alarm, Fire alarm, Alarm | alarm |
   | Vehicle horn, car horn, honking | horn |
   | Dog, Bark | dog |
   | Speech, Conversation, Narration, monologue | speech |

   Thresholds 0.3 for cues, 0.5 for speech. Log every top-3 with scores.
3. `--wav path`: play a 16 kHz mono WAV through the same buffer at real-time
   pace, print labels. Get doorbell and siren right before anything else.
4. `--mock`: no audio; cycle idle, cue(doorbell,right), speech(left),
   name(left), alarm(siren,behind) every 5 s. Wendy needs this by 7 pm; do it
   before step 5 if you're behind.
5. `state.py`: pure function of (events, now). Alarm or siren wins and holds
   until 2 s after the last detection. A cue holds 4 s; a newer cue replaces
   it. Speech only if `speakerRole != "self"`, holds while detected, fades
   3 s after. Name beats speech and cue. Emit only on change.
6. `name.py`: Porcupine on the same int16 stream in 512-sample frames.
7. Direction: if the plugin's `direction` is non-null and the 5:30 test says
   it tracks position, map it with those thresholds. Else if `/direction` is
   under 1 s old, use it. Else `near`.
8. Live with Wendy's plugin on the real glasses. Tune thresholds in hall noise.

Done when: with real glasses, a phone-played doorbell gives `cue/doorbell`
within 1 s, a siren gives `alarm` and holds, a knock gives `cue/knock`, the
name gives `name`, and 30 s of hallway noise gives nothing.

If blocked: TensorFlow won't install → `pip install ai-edge-litert`, same
`Interpreter`. YAMNet misses knocks on the G2 stream → ask Wendy to switch to
`AudioInputSource.Phone`, one line. Porcupine fights you past 9:30 → cut the
name feature, tell Dara.

### 3.3 Iurii — direction, hardware, demo rig

Everything physical, plus the direction arrow (phase 2). Phase 2 starts only
if phase 1 isn't blocked on anything.

Install, only if the ESP32 node happens: Arduino IDE 2, Boards Manager "esp32
by Espressif Systems". `WiFi.h`, `HTTPClient.h`, and `driver/i2s.h` ship with it.

Steps:
1. (5:30, with Dara) Direction test. Dara runs the plugin on real glasses
   logging `audio.direction`. You talk for 5 s from left, right, front,
   behind at 1 m. Write the numbers in `docs/direction-test.md`. Verdict:
   numbers separate by position → Tier 0 works, give Nikhil the thresholds,
   no hardware needed. Always null or noise → step 2.
2. MLH hardware table, if it exists. Ask in order: two I2S mics (INMP441,
   SPH0645, ICS-43434); or two analog mic/sound modules (KY-038, KY-037,
   MAX4466); ten male-to-female jumpers; a data USB cable for the ESP32.
   No mics → no ESP32 node; skip to step 5.
3. Wire: two mics 15 cm apart on a cardboard strip on a cap, one over each
   ear. I2S: shared SCK/WS, SD to the I2S pins, L/R select tied opposite.
   Analog: outs to GPIO 34 and 35, 3.3 V, GND.
4. Firmware: every 100 ms read both mics, RMS each,
   `margin_db = 20*log10(rms_left/rms_right)`. If `abs > 6`, POST
   `{"dir":...,"margin_db":...}` to `http://LAPTOP_IP:8000/direction`. Blink
   the LED on every POST.
5. Demo rig: the clips in section 5 on a phone; a Bluetooth speaker (a phone
   speaker is too quiet in the hall); tape L and R on the table; a cap.
6. Bench test with Nikhil's log open: correct side 9 of 10 at 1 m. Write the
   number in `docs/direction-test.md`; it's a pitch number.
7. 9 pm cutoff. Not working → unplug it, help Nikhil tune thresholds. The
   product is unchanged.

Done when: `docs/direction-test.md` says one of: Tier 0 works with thresholds;
ESP32 gives the right side 9 of 10; no direction, cut at 9 pm.

### 3.4 Dara — glasses, integration, submission

The G2, the phone, the hotspot, the Even developer portal, the Beta build,
Devpost, the video, the clock. Only you touch the Even portal.

Install: Even app 2.2.10+ signed in, developer access at
https://evenhub.evenrealities.com enabled, then fully quit and reopen the phone
app. Phone auto-lock Never. `npm i -g @evenrealities/evenhub-cli`. Devpost
project with all four and challenges Even Realities, Beyond the Digital,
Applied Intelligence.

Steps:
1. (5:20) Hotspot on the second phone. Nikhil's laptop and the iPhone join.
   LAPTOP_IP in the chat and in `README.md`. Don't toggle the hotspot; the IP
   is baked into Wendy's whitelist.
2. (5:30) Pair the G2, update firmware, run Wendy's step 1 on real glasses
   via `npx evenhub qr --url http://LAPTOP_IP:5173`, see one tap event. Do
   Iurii's direction test. Dump 30 s of PCM to a WAV while Iurii plays a
   doorbell and a siren; give it to Nikhil.
3. (6:00) Even table, closes 8 pm. Ask: does `AudioEvent.direction` carry
   data on current firmware, and in what unit? Confirm the Beta flow. Ask if
   "sound awareness for deaf users" counts as medical (it shouldn't).
4. (6:30) Pick the demo name with the team; tell Nikhil for Porcupine.
5. (7:00) Devpost skeleton: title, one-liner, the PRD demo table as prose,
   Built-with list.
6. (8:00) Throwaway pack with Wendy's `?demo=1` build:
   `npm run build && evenhub pack app.json dist -o earshot.ehpk`. Portal:
   Beta group with your email, upload under Builds, push, phone Me → Beta
   tester → install. Fix whatever breaks now, not at 8 am.
7. (9:30) Integration on real glasses, full demo script, film it rough.
8. (11:00) Checkpoint. Loop worked once, or cut in this order: name,
   direction, speech cue. Announce in the chat.
9. (12:30 am) Lock test, permission-denied test, double-tap exit.
10. (8:00 am) Final pack and Beta push. Record the 2 to 3 min video: 20 s
    pitch, six demo steps, 20 s architecture.
11. (10:00 am) Five rehearsals with someone who hasn't worn the glasses.
    README section "Install and run on G2" (Even requires it).
12. (11:00 am) Submit Devpost, confirm the Beta build. Code frozen.

Done when: Devpost and the Even Beta are both in by 11:30 am and the demo has
run five times in a row with nobody touching a laptop.

## 4. Timeline

| Time | Must be true |
|---|---|
| 5:30 pm | Template on real G2. Direction test done, verdict in `docs/`. |
| 6:00 pm | Hotspot up, LAPTOP_IP known, tools installed. |
| 7:00 pm | Server `--mock` works. Plugin renders mock states in the simulator. YAMNet labels a doorbell WAV. |
| 8:00 pm | Even table closes. Throwaway `.ehpk` installed from Beta. Mock states on real glasses. |
| 9:00 pm | Live G2 audio reaches the server. ESP32 cutoff. |
| 11:00 pm | **Full loop on real glasses, once.** Cut list decided. |
| 12:30 am | Lock, exit, permission tests pass. |
| 2:00 am | Thresholds tuned in hall noise. Sleep. |
| 8:00 am | Final pack, Beta push, video. |
| 10:00 am | Five rehearsals. README done. |
| 11:00 am | Submitted. Frozen. |

Cut order at 11 pm if the loop isn't working: name flash first, then
direction, then speech cue. Sound cue plus alarm tier plus blank-by-default is
the irreducible product.

## 5. Get and download tonight

Clips on a phone (not streamed) and as 16 kHz mono WAVs in `server/clips/`
(`ffmpeg -i in.mp3 -ar 16000 -ac 1 out.wav`): doorbell 3 s, knock 2 s, smoke
alarm 5 s, siren 5 s, car horn 2 s, dog bark 2 s, 30 s hallway noise.

Physical: Bluetooth speaker; tape and marker; everyone's chargers; a cap only
if the ESP32 node happens; from the MLH table only if it exists: 2 mic
modules, 10 jumpers, a data USB cable.

Accounts: Even developer access (Dara, before 6 pm); Picovoice and the `.ppn`
(Nikhil, by 8:30 pm); Devpost project (Dara, by 7 pm).

## 6. Submission checklist

- [ ] Devpost: description, track Beyond the Digital, challenges Even Realities
      and Applied Intelligence, public repo, 2 to 3 min video, Built-with, all four.
- [ ] Even: `.ehpk` on a Beta group, installed on Dara's phone; Even Hub app
      name on the Devpost page; README has "Install and run on G2" with any
      keys needed.
- [ ] Repo public. README: what it is, demo script, architecture, how to run
      each node, the contracts.
- [ ] Glasses, phone, laptop, speaker charged. Auto-lock off. Clips on the phone.
- [ ] One measured number for the pitch: doorbell latency; direction accuracy
      if we have it.
