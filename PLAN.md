# Earshot build plan

What we are building and why is in `PRD.md`. Background is in
`docs/RESEARCH.md`. This file says how and who.

## 1. How we work

Four pieces, four people, four laptops. Each piece is built and tested alone,
with fake inputs that live in the repo. The only thing shared is the message
formats in section 3. Nobody waits on anyone else's code. We push to GitHub
as we go and plug the pieces together over the hotspot at 9 pm, when Dara is
back from judging (away 6 to 9).

| Piece | Person | Folder | Works alone because |
|---|---|---|---|
| Glasses app | Wendy | `plugin/` | it ships with a 30 line fake server |
| Listening server | Nikhil | `server/` | it has a mock mode and takes WAV files |
| Direction node | Iurii | `firmware/` | it posts to a tiny receiver script in its own folder |
| Measurement and submission | Dara | `tools/`, `docs/`, Devpost | its scripts read the same formats and run on saved files |

Git: everyone on `main`, small commits, `git pull --rebase` before pushing.
Edit only your own folder. If you are stuck for 20 minutes, say so in the
chat.

Glasses: there is one G2. It stays with the team, paired to Wendy's phone,
so real hardware testing continues while Dara is away. The Beta install at
the end is done on whichever phone the glasses are paired to at that point.

Words used below:

- HUD: the text the wearer sees on the lenses.
- Plugin: our app. A web page that the Even phone app loads and relays to the glasses.
- PCM: raw audio samples. The glasses send 16,000 per second, 16 bit, one channel.
- YAMNet: Google's free audio classifier. Give it one second of audio and it says "doorbell, 0.82".
- Porcupine: Picovoice's keyword spotter. Trained on one word (the demo name). Runs offline.
- LAPTOP_IP: Nikhil's laptop address on the hotspot, for example `172.20.10.3`. Used only at integration.
- Beta group: how Even distributes a test build. Upload the `.ehpk` to the developer portal, assign it to a group containing your email, install from the phone.
- Tier 0: direction from the glasses' own `direction` field, no extra hardware.

## 2. The pieces

```
 G2 glasses                  iPhone running the Even app and our plugin
   │ Bluetooth: PCM           │
   │ + direction tag          │ WebSocket  ws://LAPTOP_IP:8000/ws/glasses
   │ + speakerRole            ▼
   └─────────────────▶  plugin/    Wendy
                        sends every audio event up, draws whatever state comes down
                              │
                              ▼
                        server/    Nikhil
                        YAMNet sound class, Porcupine name, state machine, direction in
                              ▲
                              │ HTTP POST http://LAPTOP_IP:8000/direction
                        firmware/  Iurii
                        ESP32 with two mics on a cap, only if mic modules exist

                        tools/     Dara
                        record.py saves what the glasses hear; eval.py scores the classifier on clips
```

## 3. Message formats

Change these only in the group chat, with everyone's ok.

Plugin to server, one JSON text frame per audio event from the glasses:
```json
{"t":"audio","pcm":"<base64 of audioPcm>","direction":1234,"speakerRole":"other","ts":1760745600123}
```
`pcm` is int16 little endian, 16 kHz, mono, exactly as the SDK gives it.
`direction` is the SDK's raw int16, or `null`. `ts` is `Date.now()`.

Server to plugin, one JSON frame each time the state changes:
```json
{"state":"cue","label":"doorbell","dir":"right","ttl_ms":4000,"level":4}
```
- `state`: `idle`, `cue`, `speech`, `name`, or `alarm`
- `label`: `doorbell`, `knock`, `siren`, `alarm`, `horn`, `dog`, `speech`, or `name`
- `dir`: `left`, `right`, `front`, `behind`, or `near`. `near` means unknown, so no arrow.
- `ttl_ms`: show for this long, then go blank. `0` means show until the next frame.
- `level`: brightness, 1 to 4

Direction node to server, HTTP POST, up to 10 per second:
```json
{"dir":"left","margin_db":8.2}
```

What the plugin draws, one text container:

| state | text | brightness | how long |
|---|---|---|---|
| idle | nothing | | until the next state |
| cue | `doorbell  ->` or `<-  knock` or `knock  (behind)` or `knock` | 4 | ttl_ms |
| speech | `speech  <-` | 2 | until idle, at least 1 s |
| name | `<-  YOUR NAME` | 4 | ttl_ms |
| alarm | `ALARM` or `SIREN` on line 1, direction on line 2 | 4 | until idle |

## 4. Who builds what

### 4.1 Wendy: the glasses app (`plugin/`)

The only code that runs on the phone and the glasses. A Vite and TypeScript
web app. The Even app loads it in a WebView and relays the display and the
touch events to the glasses over Bluetooth.

Setup:
```bash
cd ~/Projects/lahacks
npx degit even-realities/evenhub-templates/asr plugin
cd plugin && npm install && npm install @evenrealities/even_hub_sdk@0.0.16
npm run dev                                    # in one terminal
npx evenhub-simulator http://localhost:5173    # in another
```
Docs, in the order you will need them: display
https://hub.evenrealities.com/docs/build/display, audio and events
https://hub.evenrealities.com/docs/build/device-apis, network whitelist
https://hub.evenrealities.com/docs/build/networking, phone lock
https://hub.evenrealities.com/docs/build/background-lifecycle, the
`direction` field https://www.npmjs.com/package/@evenrealities/even_hub_sdk.

Your fake server, so you never need Nikhil's: `plugin/fake_server.py`, about
30 lines with the `websockets` package. It accepts the connection, ignores
what comes in, and sends one state frame from the section 3 table every 4 s.
Run it with `python fake_server.py` and point the plugin at
`ws://localhost:8000/ws/glasses` (or your own laptop's IP when testing on
the phone).

Build, in this order:

1. `app.json`: `name` Earshot, `package_id` `com.earshot.lahacks`,
   `min_sdk_version` `0.0.16`, keep `g2-microphone`, add
   `{"name":"network","desc":"Streams mic audio to the Earshot server.","whitelist":["http://SERVER:8000","ws://SERVER:8000"]}`
   where SERVER is your laptop's IP for now and Nikhil's at integration. The
   whitelist needs the exact origin; wildcards do not work.
2. `src/link.ts` replaces `src/asr/stt.ts`. Open the WebSocket. For every
   audio event send one frame in the section 3 format (base64 the
   `audioPcm`, include `direction` and `speakerRole`). On every message, call
   `render(state)`. Reconnect after 1 s if the socket closes.
3. `src/hud.ts`. One full screen text container with `isEventCapture: 1`.
   Update it only with `textContainerUpgrade`. `textColor` for brightness.
   At least 150 ms between writes. The exact strings from the section 3
   table, centered by padding with spaces.
4. `?demo=1` in the URL: skip the socket and cycle idle, cue, speech, name,
   alarm every 4 s. This is what Dara packages for the first Beta test.
5. Lifecycle. On `SYSTEM_EXIT_EVENT` or `ABNORMAL_EXIT_EVENT`: stop the audio,
   close the socket, unsubscribe. On double tap: `shutDownPageContainer(1)`.
   When the page becomes visible again (`visibilitychange`): call
   `audioControl(true, AudioInputSource.Glasses)` again and reconnect. The
   mic stream dies when the phone locks; this brings it back.
6. On the real glasses: `npx evenhub qr --url http://YOUR_IP:5173` with the
   phone on the hotspot, your fake server running. Then
   `npm run build && npx evenhub pack app.json dist -o earshot.ehpk` and
   check the packer accepts the manifest. Commit the `.ehpk`.

Done when: with your fake server, the real glasses show every row of the
section 3 table, readable and centered. Double tap exits. After the phone is
locked 5 minutes and reopened, states show again. The packer produces an
`.ehpk` without complaint.

If stuck: the simulator ignores `textColor`, so judge brightness only on
real glasses. If the phone cannot reach your laptop, it is the hotspot or the
whitelist, not your code.

### 4.2 Nikhil: the listening server (`server/`)

One Python process. It receives audio, runs the classifier and the keyword
spotter, decides what the HUD should show, and sends that to the plugin. It
also accepts direction posts from the ESP32.

Setup:
```bash
cd ~/Projects/lahacks && mkdir -p server/models server/clips && cd server
python3.12 -m venv .venv && source .venv/bin/activate     # 3.11 or 3.12; TensorFlow may not have a 3.13 wheel
pip install fastapi "uvicorn[standard]" websockets numpy tensorflow pvporcupine soundfile
```
Models into `server/models/`:
- YAMNet, TFLite version, with its class map:
  https://www.kaggle.com/models/google/yamnet/tfLite/classification-tflite.
  The class map is also at
  https://github.com/tensorflow/models/blob/master/research/audioset/yamnet/yamnet_class_map.csv.
- Porcupine: free account at https://console.picovoice.ai. Create a custom
  keyword for the demo name (the team picks it in the chat; pick a
  teammate's first name if nobody objects). Platform macOS, download the
  `.ppn`. Access key in `server/.env` as `PICOVOICE_KEY=`. Do not commit it.

Your fake inputs: `--mock` (no audio, cycles every state every 5 s) and
`--wav file.wav` (plays a clip through the pipeline at normal speed). Test
clips: download a doorbell, a knock, a smoke alarm, a siren, a car horn, a dog
bark, and 30 s of crowd noise, convert each with
`ffmpeg -i in.mp3 -ar 16000 -ac 1 clips/doorbell_1.wav`, named by label.

Build, in this order:

1. `main.py`, FastAPI. Allow all CORS origins (the Even WebView enforces
   CORS; the whitelist does not get around it). `WebSocket /ws/glasses`
   receives section 3 frames, decodes `pcm` to int16 into a rolling buffer.
   Every 0.5 s: classifier, name spotter, state machine, send if changed.
   `POST /direction` stores the latest value with a timestamp. `GET /` is a
   status page. Also log the `direction` and `speakerRole` of every frame to
   the console; that is the Tier 0 test.
2. `--mock` flag. Do this before anything else; it lets Wendy and Dara test
   against a real server later without your classifier being done.
3. `classify.py`. `tf.lite.Interpreter` on `yamnet.tflite`. Run the last
   15600 samples as float32 in -1 to 1. Top 3 classes. Map YAMNet names to
   ours:

   | YAMNet class name contains | our label |
   |---|---|
   | Doorbell | doorbell |
   | Knock | knock |
   | Siren, Civil defense siren, Police car (siren), Ambulance (siren), Fire engine, fire truck (siren) | siren |
   | Smoke detector, smoke alarm, Fire alarm, Alarm | alarm |
   | Vehicle horn, car horn, honking | horn |
   | Dog, Bark | dog |
   | Speech, Conversation, Narration, monologue | speech |

   Threshold 0.3 for cues, 0.5 for speech. Log every top 3 with scores.
4. `--wav` flag. Get doorbell and siren right before anything else.
5. `state.py`, a plain function of (events, direction, now) that returns a
   state frame or None if nothing changed. Rules:
   - alarm or siren gives `alarm`, holds until 2 s after the last detection, suppresses everything else
   - name gives `name` for 4 s, beats speech and cue
   - any other cue gives `cue` for 4 s; a newer cue replaces an older one
   - speech with `speakerRole != "self"` gives `speech`; holds while detected, fades 3 s after, stays at least 1 s
   - otherwise `idle`
   - `dir` is the most recent direction under 1 s old, from the glasses tag if it maps, else from `/direction`, else `near`
   A few asserts in `test_state.py`: two sounds at once, alarm then doorbell,
   speech from self, direction expiring.
6. `name.py`. Porcupine on the same int16 stream in 512 sample frames.

Done when: `python main.py --wav clips/doorbell_1.wav` prints a
`cue/doorbell` state within 1 s of the sound; siren gives `alarm` and holds;
`noise_1.wav` prints nothing; `--mock` cycles all five states; the asserts
pass.

If stuck: TensorFlow will not install, use `pip install ai-edge-litert`, same
`Interpreter`. Porcupine will not cooperate, leave `name.py` as a stub that
never fires and move on.

### 4.3 Iurii: the direction node (`firmware/`)

Direction is the arrow on each cue. It is the one thing the glasses may not
be able to do alone. Two possible sources, and you own finding out which.

First, the question that decides everything: does the G2's own `direction`
field carry data? Nikhil's server prints it per frame once Wendy's plugin
streams to it, and Wendy's fake server does not, so this test needs both of
their step 1s done and the glasses. Until then, work on the ESP32 node, which
is useful either way as a backup.

Setup: Arduino IDE 2, Boards Manager "esp32 by Espressif Systems". `WiFi.h`,
`HTTPClient.h`, and `driver/i2s.h` come with it.

Parts: the plain ESP32 board we have, the breadboard, and from the MLH
hardware table if there is one: two I2S microphone modules (INMP441,
SPH0645, ICS-43434), or two analog sound modules (KY-038, KY-037, MAX4466);
ten male to female jumper wires; a USB data cable for the board. No
microphones means no ESP32 node.

Your fake receiver, so you never need Nikhil's server:
`firmware/receiver.py`, 15 lines of FastAPI with one `POST /direction` that
prints what it receives. Run it on your laptop; the ESP32 posts to your IP.

Build:

1. Wire two mics 15 cm apart on a strip of cardboard that sits on a cap, one
   over each ear. I2S: share SCK and WS, each SD to an I2S pin, L/R select
   pins tied opposite. Analog: outputs to GPIO 34 and 35, 3.3 V, ground.
2. `firmware/direction/direction.ino`. Join the hotspot in `setup()`. Every
   100 ms read both mics, RMS of each, `margin_db = 20 * log10(rms_left /
   rms_right)`. If the absolute value is over 6, POST
   `{"dir":"left" or "right","margin_db":x}` to `http://RECEIVER_IP:8000/direction`.
   Blink the LED on every POST.
3. Bench test with your receiver printing. Talk from the left and the right
   at 1 m. Write the hit rate in `docs/direction-test.md`.
4. The Tier 0 test, as soon as Wendy's plugin streams into Nikhil's server:
   stand 1 m away, talk 5 s from left, right, front, behind, say which
   position you are in, and have Nikhil read the `direction` numbers off his
   log. Write them in `docs/direction-test.md` with the verdict. If they
   separate by position, give Nikhil the thresholds and the ESP32 is a
   backup. If always null or random, the ESP32 is the arrow.
5. Demo rig: a Bluetooth speaker (a phone speaker is too quiet in the hall),
   the clips on a phone, L and R taped on the table, a cap for the mic strip.

Done when: `docs/direction-test.md` has the Tier 0 numbers and a verdict, and
either the ESP32 posts the correct side 9 of 10 at 1 m or the file says we
ship without the arrow.

### 4.4 Dara: measurement, glasses, submission (`tools/`, `docs/`, Devpost)

Away 6 to 9. Everything here either happens before 6, after 9, or runs on
files other people push.

Setup:
```bash
cd ~/Projects/lahacks && mkdir -p tools
python3.12 -m venv .venv && source .venv/bin/activate
pip install websockets numpy soundfile tensorflow
npm i -g @evenrealities/evenhub-cli
```
Even app 2.2.10 or newer, signed in, developer access on at
https://evenhub.evenrealities.com, then fully quit and reopen the phone app.
Auto lock Never. Devpost project with all four and the challenges Even
Realities, Beyond the Digital, Applied Intelligence.

Before 6:
1. Hotspot on the second phone; your iPhone and Wendy's phone join it.
2. Go to the Even table (open until 8). Ask whether `AudioEvent.direction`
   carries data on current firmware and in what unit, confirm the Beta group
   flow, and ask whether "sound awareness for deaf users" is considered
   medical. It should not be; hear them say it.
3. Devpost project created, the PRD demo table turned into the description.

After 9, code:
4. `tools/record.py`. A WebSocket server on port 8000 that accepts the
   plugin's frames and writes `--out name.wav` (16 kHz mono) and `name.jsonl`
   with `ts`, `direction`, `speakerRole`, RMS per frame. Point the plugin at
   your laptop, record 30 s each of silence, a doorbell, a siren, knocks,
   and someone talking from four sides. These are the ground truth clips.
5. `tools/eval.py`. Loads YAMNet itself (same 20 lines as Nikhil's
   `classify.py`, copied, so this never depends on his code being in a
   runnable state) and runs every WAV in `server/clips/` and your recordings
   in 0.5 s steps. Prints expected label, top label, top score, and time to
   first correct, then a confusion table. This is where the pitch numbers and
   the threshold choices come from.
6. If the Tier 0 numbers in `docs/direction-test.md` separate by position,
   write the mapping from the tag to left, right, front, behind and send it
   to Nikhil in the chat.

After 9, integration and submission:
7. Nikhil's laptop runs `python main.py`; Wendy's `app.json` whitelist gets
   Nikhil's IP; the ESP32 posts to Nikhil's IP. Run the demo script from the
   PRD start to finish. Film it rough; that is the backup video.
8. Package Wendy's build and push it to a Beta group under your account.
   Install from Me, then Beta tester, on the phone the G2 is paired to; add
   that phone's Even account email to the Beta group. Lock the phone 5 minutes, reopen, check
   states resume. Deny the mic permission once and check nothing crashes.
9. Sunday morning: final package and Beta push, the 2 to 3 minute video
   (20 s pitch, the six demo steps, 20 s on how it works), the README section
   "Install and run on G2", five rehearsals with someone who has not worn the
   glasses, submit.

Done when: `eval.py` prints a table with doorbell and siren correct; Devpost
and the Even Beta are both in by 11:30 am Sunday; the demo has run five times
in a row with nobody touching a laptop.

## 5. Checkpoints

| When | Must be true |
|---|---|
| 9:00 pm | Each piece passes its own "done when" test, or its owner says what is missing. Integration starts. |
| 11:00 pm | The full loop has worked on the real glasses once. If not, cut: name flash first, then direction, then speech cue. Sound cue, alarm, and blank by default do not get cut. |
| 8:00 am | Final package, Beta push, video. |
| 11:00 am | Submitted. Code frozen. |
| 12:00 pm | Deadline. Judging follows. Glasses, phone, laptop, speaker charged. |

## 6. Submission checklist

- [ ] Devpost: description, track Beyond the Digital, challenges Even Realities and Applied Intelligence, public repo, 2 to 3 minute video, "Built with", all four members.
- [ ] Even: `.ehpk` on a Beta group and installed on the phone the G2 is paired to. The app name on the Devpost page. README section "Install and run on G2" listing any keys needed.
- [ ] Repo public. README: what it is, the demo script, the diagram from section 2, how to run each piece, the formats from section 3.
- [ ] One measured number for the pitch from `eval.py`: doorbell latency. Direction accuracy if we have it.
