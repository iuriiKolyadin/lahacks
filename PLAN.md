# Earshot — build plan

How, who, when. The what and why are in `PRD.md`. Background is in
`docs/RESEARCH.md`.

**How to use this file:** read section 0 (your first 10 minutes), section 1
(the picture), section 2 (the contracts), then only your own part of
section 4. Check the timeline in section 5 once an hour.

## 0. Start here: your first 10 minutes

| Who | Do this now | Then |
|---|---|---|
| **Wendy** | `cd ~/Projects/lahacks && npx degit even-realities/evenhub-templates/asr plugin && cd plugin && npm install` | Section 4.1 |
| **Nikhil** | `cd ~/Projects/lahacks && mkdir -p server && cd server && python3.12 -m venv .venv && source .venv/bin/activate && pip install fastapi "uvicorn[standard]" websockets numpy tensorflow pvporcupine` | Section 4.2 |
| **Iurii** | Find out if there is an MLH hardware table. If yes, go ask for two microphone modules (names in 4.3 step 2). | Section 4.3 |
| **Dara** | Turn on the hotspot on the second phone, join it from the iPhone and Nikhil's laptop, post Nikhil's laptop IP in the chat as `LAPTOP_IP`. | Section 4.4 |

Words used in this file:
- **HUD**: the text the wearer sees on the glasses lenses.
- **Plugin**: our app. A web page the Even phone app loads and relays to the glasses.
- **Server**: a Python program on Nikhil's laptop that listens to audio and decides what the HUD shows.
- **PCM**: raw audio samples. The glasses send 16,000 per second, 16-bit, one channel.
- **YAMNet**: Google's free audio classifier. Give it 1 s of audio, it says "doorbell 0.82".
- **Porcupine**: Picovoice's keyword spotter. Trained on one word (the demo name), runs offline.
- **LAPTOP_IP**: the IP of Nikhil's laptop on the hotspot, e.g. `172.20.10.3`. Posted in the chat by Dara.
- **Beta group**: how Even distributes a test build. Upload the `.ehpk` to the developer portal, assign it to a group containing your email, install from the phone.
- **Tier 0**: direction from the glasses' own `direction` field, no extra hardware.
- **Phase 1**: everything that works with the G2 mic alone (no direction arrow). Due 11 pm.
- **Phase 2**: the direction arrow. Only after phase 1 works.

Git rules: everyone commits to `main`, small commits, `git pull --rebase`
before every push. Each person edits only their own folder (`plugin/`,
`server/`, `firmware/`, `tools/`) plus `docs/`. Shared files (`PRD.md`,
`PLAN.md`, `README.md`) are edited by Dara only; send changes in the chat.

## 1. Architecture

Four pieces of code, four owners.

```
 G2 (4-mic array)            iPhone: Even app running our plugin
   │ BLE: 16 kHz PCM          │
   │ + direction tag          │ WebSocket  ws://LAPTOP_IP:8000/ws/glasses
   │ + speakerRole            ▼
   └─────────────────▶  plugin/   (TypeScript, Wendy)
                        - sends every audio event up
                        - renders whatever state comes down
                              │
                              ▼
                        server/   (Python, Nikhil: plumbing + classifier + name)
                        - main.py: WebSocket in, state out, /direction in
                        - classify.py: YAMNet → sound class every 0.5 s
                        - name.py: Porcupine → name event
                        - state.py: the brain  (Dara)
                          events + direction → one HUD state
                              ▲
                              │ HTTP POST http://LAPTOP_IP:8000/direction
                        firmware/  ESP32 + 2 mics on a cap  (Arduino, Iurii) — phase 2 only

                        tools/    (Python, Dara)
                        - record.py: save G2 audio + direction tags to WAV
                        - eval.py: run every clip through the classifier, print accuracy + latency
```

Every piece has a stand-in so nobody waits:
- `python main.py --mock` cycles through every HUD state every 5 s with no audio. Wendy builds against this.
- `plugin` with `?demo=1` in the URL cycles states locally with no server. Dara packages against this.
- `python main.py --wav clips/doorbell.wav` feeds a clip through the classifier with no glasses. Nikhil tests against this.
- `state.py` is a pure function. Dara tests it with plain Python asserts, no hardware.

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

**Inside the server: classifier and name spotter to the state machine**
```python
Event(kind="sound", label="doorbell", score=0.82, ts=...)
Event(kind="name", ts=...)
Event(kind="speech", speaker="other", ts=...)       # speaker: "self" | "other" | "unknown"
Direction(dir="left", source="g2"|"esp32", ts=...)  # or None
state.update(events: list[Event], direction: Direction | None, now: float) -> HudState | None   # None = unchanged
```

**HUD rendering, one text container, exact strings**

| state | text | brightness | hold |
|---|---|---|---|
| idle | `` (empty) | - | until next |
| cue | `doorbell  ->`, `<-  knock`, `knock  (behind)`, `knock` | 4 | ttl_ms |
| speech | `speech  <-` | 2 | until idle, at least 1 s |
| name | `<-  YOUR NAME` | 4 | ttl_ms |
| alarm | line 1 `ALARM` or `SIREN`, line 2 direction | 4 | until idle |

## 3. Running things

```bash
# server (Nikhil's laptop)
cd server && source .venv/bin/activate
python main.py                       # real mode, listens on 0.0.0.0:8000
python main.py --mock                # fake states every 5 s
python main.py --wav clips/doorbell.wav

# plugin (Wendy's laptop, or Dara's for packaging)
cd plugin && npm run dev             # dev server on 0.0.0.0:5173
npx evenhub-simulator http://localhost:5173          # desktop simulator
npx evenhub qr --url http://LAPTOP_IP:5173            # scan from the Even app to load on real glasses
npm run build && npx evenhub pack app.json dist -o earshot.ehpk   # package for Beta

# tools (Dara's laptop)
python tools/record.py --out clips/session1.wav      # saves what the glasses hear, with direction tags
python tools/eval.py                                 # accuracy + latency table over clips/
```

## 4. Who does what

Rules: do your steps in order, run your "done when" test, say so in the chat.
Stuck 20 minutes: say so in the chat. Dara reassigns.

### 4.1 Wendy — plugin (`plugin/`)

The only code that runs on the phone and the glasses. A Vite + TypeScript web
app; the Even app loads it in a WebView and relays display and input to the
glasses over Bluetooth.

Install (after the section 0 command):
```bash
cd plugin && npm install @evenrealities/even_hub_sdk@0.0.16   # template pins 0.0.10; 0.0.16 adds `direction`
```
Docs, in the order you'll need them:
display https://hub.evenrealities.com/docs/build/display ·
device APIs https://hub.evenrealities.com/docs/build/device-apis ·
networking https://hub.evenrealities.com/docs/build/networking ·
lifecycle https://hub.evenrealities.com/docs/build/background-lifecycle ·
SDK README (the `direction` field) https://www.npmjs.com/package/@evenrealities/even_hub_sdk

Steps:
1. (5:45) `npm run dev`, then `npx evenhub-simulator http://localhost:5173`.
   The template's "Listening…" shows in the simulator.
2. (6:00) `app.json`: `name` Earshot, `package_id` `com.earshot.lahacks`,
   `min_sdk_version` `0.0.16`, keep `g2-microphone`, add
   `{"name":"network","desc":"Streams mic audio to the Earshot server.","whitelist":["http://LAPTOP_IP:8000","ws://LAPTOP_IP:8000"]}`
   with the real IP. Exact origins, no wildcards.
3. (6:15) Replace `src/asr/stt.ts` with `src/link.ts`: open a WebSocket to
   `ws://LAPTOP_IP:8000/ws/glasses`, send one frame per audio event in the
   section 2 format (base64 the `audioPcm`, include `direction` and
   `speakerRole`), call `render(state)` on every message, reconnect with 1 s
   backoff on close.
4. (7:00) `src/hud.ts`: one full-screen text container with
   `isEventCapture: 1`, updated only with `textContainerUpgrade`, `textColor`
   for brightness, 150 ms debounce, strings from the section 2 table,
   centered by padding with spaces.
5. (7:30) `?demo=1` in the URL: skip the socket, cycle idle, cue, speech,
   name, alarm every 4 s. Also `?record=1`: same as normal, but Dara's
   `record.py` is the server; nothing extra to do, just don't crash if the
   server never sends a state.
6. (8:00) Lifecycle: on `SYSTEM_EXIT_EVENT` / `ABNORMAL_EXIT_EVENT` stop
   audio, close the socket, unsubscribe. Double-tap calls
   `shutDownPageContainer(1)`. On `visibilitychange` to visible, re-call
   `audioControl(true, AudioInputSource.Glasses)` and reconnect, because the
   mic stream dies when the phone locks.
7. (8:30) Real glasses with Dara: `npx evenhub qr --url http://LAPTOP_IP:5173`,
   then against Nikhil's `--mock` server.

Done when: the mock server makes the real G2 show every row of the HUD table,
readable and centered; double-tap exits; after a 5-minute phone lock the
states resume.

If blocked: the simulator ignores `textColor`; don't tune brightness there.
Phone can't reach the laptop: it's the hotspot or the whitelist, not your code.

### 4.2 Nikhil — server plumbing, classifier, name spotter (`server/`)

One Python process. Receives audio, runs the classifier and the keyword
spotter, hands events to Dara's `state.py`, pushes the result to the plugin.

Install (after the section 0 command), models into `server/models/`:
- YAMNet TFLite + class map: https://www.kaggle.com/models/google/yamnet/tfLite/classification-tflite
  (class map also at https://github.com/tensorflow/models/blob/master/research/audioset/yamnet/yamnet_class_map.csv)
- Porcupine: free account at https://console.picovoice.ai, custom keyword =
  the demo name (Dara tells you by 6:30), platform macOS, download the
  `.ppn`. Access key in `server/.env` as `PICOVOICE_KEY=`. Never commit it.

Steps:
1. (6:00) `main.py`: FastAPI. CORS `allow_origins=["*"]`. `WebSocket
   /ws/glasses` takes the section 2 frames, decodes `pcm` to int16 into a
   rolling buffer, and every 0.5 s calls the classifier, the name spotter,
   then `state.update(...)`, and sends the result if not None.
   `POST /direction` stores the latest value with a timestamp. `GET /` is a
   status page. `--mock` flag: skip audio, cycle idle, cue(doorbell,right),
   speech(left), name(left), alarm(siren,behind) every 5 s. **Wendy needs
   `--mock` by 7 pm; do it first.**
2. (6:45) `classify.py`: `tf.lite.Interpreter` on `yamnet.tflite`. Run the
   last 15600 samples as float32 in [-1, 1]. Top 3 classes. Map AudioSet
   names to ours:

   | YAMNet class contains | ours |
   |---|---|
   | Doorbell | doorbell |
   | Knock | knock |
   | Siren, Civil defense siren, Police car (siren), Ambulance (siren), Fire engine, fire truck (siren) | siren |
   | Smoke detector, smoke alarm, Fire alarm, Alarm | alarm |
   | Vehicle horn, car horn, honking | horn |
   | Dog, Bark | dog |
   | Speech, Conversation, Narration, monologue | speech |

   Thresholds 0.3 for cues, 0.5 for speech. Emit `Event(kind="sound", ...)`
   or `Event(kind="speech", speaker=<speakerRole from the frame>)`. Log every
   top-3 with scores.
3. (7:30) `--wav path`: play a 16 kHz mono WAV through the same buffer at
   real-time pace, print events. Get doorbell and siren right before
   anything else.
4. (8:30) `name.py`: Porcupine on the same int16 stream in 512-sample
   frames. Emit `Event(kind="name")`.
5. (9:30) Live with Wendy's plugin on the real glasses, Dara's `state.py`
   plugged in. Tune thresholds in hall noise using Dara's `eval.py` output.

Done when: with real glasses, a phone-played doorbell gives a `sound/doorbell`
event within 1 s, a siren gives `sound/siren`, a knock gives `sound/knock`, the
name gives `name`, and 30 s of hallway noise gives nothing above threshold.

If blocked: TensorFlow won't install → `pip install ai-edge-litert`, same
`Interpreter`. YAMNet misses knocks on the G2 stream → ask Wendy to switch to
`AudioInputSource.Phone`, one line. Porcupine fights you past 9:30 → cut the
name feature, tell Dara.

### 4.3 Iurii — direction hardware and demo rig (`firmware/`)

Everything physical, plus the direction arrow (phase 2). Phase 2 starts only
if phase 1 isn't blocked on anything.

Install, only if the ESP32 node happens: Arduino IDE 2, Boards Manager "esp32
by Espressif Systems". `WiFi.h`, `HTTPClient.h`, and `driver/i2s.h` ship with it.

Steps:
1. (5:30, with Dara) Direction test. Dara runs `record.py` with the plugin on
   real glasses. You talk for 5 s from left, right, front, behind at 1 m,
   announcing each position. Dara writes the numbers in
   `docs/direction-test.md`. Verdict: numbers separate by position → Tier 0
   works, no hardware needed. Always null or noise → step 2.
2. (6:00) MLH hardware table, if it exists. Ask in order: two I2S mics
   (INMP441, SPH0645, ICS-43434); or two analog mic/sound modules (KY-038,
   KY-037, MAX4466); ten male-to-female jumpers; a data USB cable for the
   ESP32. No mics → no ESP32 node; skip to step 5.
3. (6:30) Wire: two mics 15 cm apart on a cardboard strip on a cap, one over
   each ear. I2S: shared SCK/WS, SD to the I2S pins, L/R select tied
   opposite. Analog: outs to GPIO 34 and 35, 3.3 V, GND.
4. (7:30) Firmware `firmware/direction/direction.ino`: join the hotspot in
   `setup()`. Every 100 ms read both mics, RMS each,
   `margin_db = 20*log10(rms_left/rms_right)`. If `abs > 6`, POST
   `{"dir":"left"|"right","margin_db":x}` to
   `http://LAPTOP_IP:8000/direction`. Blink the LED on every POST.
5. (8:00) Demo rig: the clips in section 6 on a phone; a Bluetooth speaker
   (a phone speaker is too quiet in the hall); tape L and R on the table; a
   cap for the mic strip.
6. (8:30) Bench test with Nikhil's server log open: correct side 9 of 10 at
   1 m. Write the number in `docs/direction-test.md`.
7. (9:00) Cutoff. Not working → unplug it, help Nikhil tune thresholds. The
   product is unchanged.

Done when: `docs/direction-test.md` says one of: Tier 0 works with
thresholds; ESP32 gives the right side 9 of 10; no direction, cut at 9 pm.

### 4.4 Dara — state machine, eval harness, glasses, submission (`server/state.py`, `tools/`)

Two code pieces, plus the things only you can do because they're your phone
and your accounts.

Install:
```bash
cd ~/Projects/lahacks && mkdir -p tools server/clips
python3.12 -m venv .venv && source .venv/bin/activate
pip install fastapi "uvicorn[standard]" websockets numpy soundfile
npm i -g @evenrealities/evenhub-cli
```
Even app 2.2.10+ signed in; developer access at https://evenhub.evenrealities.com
enabled, then fully quit and reopen the phone app; phone auto-lock Never.
Devpost project with all four, challenges Even Realities, Beyond the Digital,
Applied Intelligence.

**Code steps**
1. (5:20) `tools/record.py`: a tiny WebSocket server on port 8000 that
   accepts the plugin's section 2 frames and writes `--out file.wav` (16 kHz
   mono) plus `file.jsonl` with one line per frame: `ts`, `direction`,
   `speakerRole`, RMS. Prints direction live so the 5:30 test is just
   watching the terminal. Point Wendy's plugin at your laptop for this test.
2. (5:30) Run the direction test with Iurii (his step 1). Record 30 s of
   each: silence, Iurii talking from four positions, a doorbell clip, a siren
   clip, a knock. Write `docs/direction-test.md`: a table of position vs
   the `direction` values seen, and the verdict. Give the WAVs to Nikhil.
3. (6:30) `server/state.py`: the pure function from section 2. Rules:
   - alarm or siren → `alarm`, holds until 2 s after the last detection,
     suppresses everything else;
   - `name` → `name`, 4 s, beats speech and cue;
   - any other cue → `cue`, 4 s, a newer cue replaces an older one;
   - speech with `speaker != "self"` → `speech`, holds while detected,
     fades 3 s after, minimum 1 s on screen;
   - otherwise `idle`;
   - `dir` comes from the most recent `Direction` under 1 s old, else `near`;
   - return `None` when nothing changed, so the plugin isn't spammed.
   Write `server/test_state.py` with plain asserts: two sounds at once,
   alarm then doorbell, speech from self, direction expiring. Run with
   `python -m pytest server/` or just `python server/test_state.py`.
4. (7:30) `tools/eval.py`: for every WAV in `server/clips/`, run Nikhil's
   `classify.py` over it in 0.5 s steps and print: expected label (from the
   filename), top label, top score, and time-to-first-correct. Then a
   confusion table. This is the pitch number and the threshold-tuning tool.
5. (9:00) Direction mapping: if Tier 0 works, write `direction_from_tag(int)
   -> "left"|"right"|"front"|"behind"` in `state.py` from your test table.
   Else wire `/direction` from the ESP32. Else `near`.

**Logistics steps** (interleave; none takes more than 20 minutes)
6. (6:00) Even table, closes 8 pm. Ask: does `AudioEvent.direction` carry
   data on current firmware, and in what unit? Confirm the Beta flow. Ask if
   "sound awareness for deaf users" counts as medical (it shouldn't).
7. (6:30) Pick the demo name with the team; tell Nikhil for Porcupine.
8. (8:00) Throwaway pack with Wendy's `?demo=1` build: `npm run build &&
   npx evenhub pack app.json dist -o earshot.ehpk`. Portal: Beta group with
   your email, upload under Builds, push, phone Me → Beta tester → install.
   Fix whatever breaks now, not at 8 am.
9. (9:30) Integration on real glasses, full demo script, film it rough.
10. (11:00) Checkpoint. Loop worked once, or cut in this order: name,
    direction, speech cue. Announce in the chat.
11. (12:30 am) Lock test, permission-denied test, double-tap exit.
12. (8:00 am) Final pack and Beta push. Record the 2 to 3 min video: 20 s
    pitch, six demo steps, 20 s architecture. Devpost page (skeleton can be
    written any time you're waiting on someone).
13. (10:00 am) Five rehearsals with someone who hasn't worn the glasses.
    README section "Install and run on G2" (Even requires it).
14. (11:00 am) Submit Devpost, confirm the Beta build. Code frozen.

Done when: `test_state.py` passes; `eval.py` prints a table with doorbell and
siren correct; `docs/direction-test.md` has a verdict; Devpost and the Even
Beta are both in by 11:30 am; the demo has run five times in a row with
nobody touching a laptop.

## 5. Timeline

| Time | Must be true |
|---|---|
| 5:30 pm | Template on real G2. `record.py` capturing. Direction test done, verdict in `docs/`. |
| 6:00 pm | Hotspot up, LAPTOP_IP known, tools installed. |
| 7:00 pm | Server `--mock` works. Plugin renders mock states in the simulator. YAMNet labels a doorbell WAV. `state.py` tests pass. |
| 8:00 pm | Even table closes. Throwaway `.ehpk` installed from Beta. Mock states on real glasses. `eval.py` prints a table. |
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

## 6. Get and download tonight

Clips on a phone (not streamed) and as 16 kHz mono WAVs in `server/clips/`
named by label, e.g. `doorbell_1.wav` (`ffmpeg -i in.mp3 -ar 16000 -ac 1
out.wav`): doorbell 3 s, knock 2 s, smoke alarm 5 s, siren 5 s, car horn 2 s,
dog bark 2 s, 30 s hallway noise as `noise_1.wav`. Iurii downloads; Dara
converts.

Physical: Bluetooth speaker; tape and marker; everyone's chargers; a cap only
if the ESP32 node happens; from the MLH table only if it exists: 2 mic
modules, 10 jumpers, a data USB cable.

Accounts: Even developer access (Dara, before 6 pm); Picovoice and the `.ppn`
(Nikhil, by 8:30 pm); Devpost project (Dara, by 7 pm).

## 7. Submission checklist

- [ ] Devpost: description, track Beyond the Digital, challenges Even Realities
      and Applied Intelligence, public repo, 2 to 3 min video, Built-with, all four.
- [ ] Even: `.ehpk` on a Beta group, installed on Dara's phone; Even Hub app
      name on the Devpost page; README has "Install and run on G2" with any
      keys needed.
- [ ] Repo public. README: what it is, demo script, architecture, how to run
      each piece, the contracts.
- [ ] Glasses, phone, laptop, speaker charged. Auto-lock off. Clips on the phone.
- [ ] One measured number for the pitch from `eval.py`: doorbell latency;
      direction accuracy if we have it.
