# Earshot build plan

What we are building and why is in `PRD.md`. Background is in
`docs/RESEARCH.md`. This file says how, who, and when.

Read section 1, then your own part of section 4. Check section 5 once an hour.

## 1. Your first 10 minutes

| Who | Do this now |
|---|---|
| Wendy | `cd ~/Projects/lahacks && npx degit even-realities/evenhub-templates/asr plugin && cd plugin && npm install && npm install @evenrealities/even_hub_sdk@0.0.16` |
| Nikhil | `cd ~/Projects/lahacks && mkdir -p server/models server/clips && cd server && python3.12 -m venv .venv && source .venv/bin/activate && pip install fastapi "uvicorn[standard]" websockets numpy tensorflow pvporcupine` |
| Iurii | Find out whether there is an MLH hardware table. If there is, ask for two microphone modules. Names are in section 4.3, step 2. |
| Dara | Turn on the hotspot on the second phone. Join it from the iPhone and from Nikhil's laptop. Post Nikhil's laptop IP in the chat as `LAPTOP_IP`. |

Words used below:

- HUD: the text the wearer sees on the lenses.
- Plugin: our app. A web page that the Even phone app loads and relays to the glasses.
- Server: a Python program on Nikhil's laptop. It listens to the audio and decides what the HUD shows.
- PCM: raw audio samples. The glasses send 16,000 per second, 16 bit, one channel.
- YAMNet: Google's free audio classifier. Give it one second of audio and it says "doorbell, 0.82".
- Porcupine: Picovoice's keyword spotter. Trained on one word (the demo name). Runs offline.
- LAPTOP_IP: Nikhil's laptop address on the hotspot, for example `172.20.10.3`.
- Beta group: how Even distributes a test build. Upload the `.ehpk` to the developer portal, assign it to a group that contains your email, install from the phone.
- Tier 0: direction from the glasses' own `direction` field. No extra hardware.
- Phase 1: everything that works with the G2 mic alone. No direction arrow. Due 11 pm.
- Phase 2: the direction arrow. Starts only after phase 1 works.

Git: everyone commits to `main`. Small commits. `git pull --rebase` before
every push. Edit only your own folder (`plugin/`, `server/`, `firmware/`,
`tools/`) and `docs/`. Dara edits `PRD.md`, `PLAN.md`, and `README.md`; send
changes to those in the chat.

## 2. The pieces

```
 G2 glasses                  iPhone running the Even app and our plugin
   │ Bluetooth: PCM           │
   │ + direction tag          │ WebSocket  ws://LAPTOP_IP:8000/ws/glasses
   │ + speakerRole            ▼
   └─────────────────▶  plugin/    TypeScript      Wendy
                        sends every audio event up, draws whatever state comes down
                              │
                              ▼
                        server/    Python
                        main.py       WebSocket in, state out, /direction in   Nikhil
                        classify.py   YAMNet, sound class every 0.5 s          Nikhil
                        name.py       Porcupine, name event                     Nikhil
                        state.py      events + direction → one HUD state        Dara
                              ▲
                              │ HTTP POST http://LAPTOP_IP:8000/direction
                        firmware/  ESP32 with two mics on a cap    Iurii, phase 2 only

                        tools/     Python                           Dara
                        record.py  saves what the glasses hear, with direction tags
                        eval.py    runs every clip through the classifier, prints accuracy and latency
```

Each piece can run without the others:

- `python main.py --mock` cycles through every HUD state every 5 s. Wendy builds the plugin against this.
- The plugin with `?demo=1` in its URL cycles states on its own. Dara packages against this.
- `python main.py --wav clips/doorbell.wav` feeds one clip through the classifier. Nikhil tests against this.
- `state.py` is a plain function. Dara tests it with asserts.

## 3. Contracts

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

ESP32 to server, HTTP POST, up to 10 per second:
```json
{"dir":"left","margin_db":8.2}
```

Inside the server, from the classifier and name spotter to the state machine:
```python
Event(kind="sound", label="doorbell", score=0.82, ts=...)
Event(kind="name", ts=...)
Event(kind="speech", speaker="other", ts=...)        # "self", "other", or "unknown"
Direction(dir="left", source="g2", ts=...)           # source "g2" or "esp32"; may be None
state.update(events, direction, now) -> HudState | None   # None means nothing changed
```

What the plugin draws, one text container:

| state | text | brightness | how long |
|---|---|---|---|
| idle | nothing | | until the next state |
| cue | `doorbell  ->` or `<-  knock` or `knock  (behind)` or `knock` | 4 | ttl_ms |
| speech | `speech  <-` | 2 | until idle, at least 1 s |
| name | `<-  YOUR NAME` | 4 | ttl_ms |
| alarm | `ALARM` or `SIREN` on line 1, direction on line 2 | 4 | until idle |

## 4. Who does what

Do your steps in order. When your "done when" test passes, say so in the
chat. If you are stuck for 20 minutes, say so in the chat and Dara reassigns.

### 4.1 Wendy: the plugin (`plugin/`)

This is the only code that runs on the phone and the glasses. It is a Vite
and TypeScript web app. The Even app loads it in a WebView and relays the
display and the touch events to the glasses over Bluetooth.

Docs, in the order you will need them:
- display: https://hub.evenrealities.com/docs/build/display
- audio and events: https://hub.evenrealities.com/docs/build/device-apis
- network whitelist: https://hub.evenrealities.com/docs/build/networking
- phone lock behaviour: https://hub.evenrealities.com/docs/build/background-lifecycle
- the `direction` field: https://www.npmjs.com/package/@evenrealities/even_hub_sdk

Steps:

1. 5:45. Run `npm run dev`, then in a second terminal
   `npx evenhub-simulator http://localhost:5173`. The template's
   "Listening…" text should show in the simulator.
2. 6:00. Edit `app.json`. Set `name` to `Earshot`, `package_id` to
   `com.earshot.lahacks`, `min_sdk_version` to `0.0.16`. Keep the
   `g2-microphone` permission. Add a network permission with the real IP:
   `{"name":"network","desc":"Streams mic audio to the Earshot server.","whitelist":["http://LAPTOP_IP:8000","ws://LAPTOP_IP:8000"]}`.
   The whitelist needs the exact origin. Wildcards do not work.
3. 6:15. Replace `src/asr/stt.ts` with `src/link.ts`. Open a WebSocket to
   `ws://LAPTOP_IP:8000/ws/glasses`. For every audio event, send one frame in
   the section 3 format: base64 the `audioPcm`, and include `direction` and
   `speakerRole`. On every message from the server, call `render(state)`. If
   the socket closes, reconnect after 1 s.
4. 7:00. Write `src/hud.ts`. One full screen text container with
   `isEventCapture: 1`. Update it only with `textContainerUpgrade`. Use
   `textColor` for brightness. Wait at least 150 ms between writes. Use the
   exact strings from the section 3 table. Center by padding with spaces.
5. 7:30. If the URL has `?demo=1`, skip the socket and cycle idle, cue,
   speech, name, alarm every 4 s.
6. 8:00. Lifecycle. On `SYSTEM_EXIT_EVENT` or `ABNORMAL_EXIT_EVENT`, stop the
   audio, close the socket, unsubscribe. On double tap, call
   `shutDownPageContainer(1)`. When the page becomes visible again (the
   `visibilitychange` event), call `audioControl(true,
   AudioInputSource.Glasses)` again and reconnect. The mic stream dies when
   the phone locks, so this is what brings it back.
7. 8:30. Test on the real glasses with Dara: `npx evenhub qr --url
   http://LAPTOP_IP:5173`. Then run it against Nikhil's `--mock` server.

Done when: with the mock server running, the real glasses show every row of
the section 3 table, readable and centered. Double tap exits. After the phone
has been locked for 5 minutes and reopened, states show up again.

If stuck: the simulator ignores `textColor`, so judge brightness only on the
real glasses. If the phone cannot reach the laptop, the problem is the hotspot
or the whitelist, so ask Dara before you debug your code.

### 4.2 Nikhil: server plumbing, classifier, name spotter (`server/`)

One Python process. It receives the audio, runs the classifier and the keyword
spotter, hands the events to Dara's `state.py`, and sends the result to the
plugin.

Models, into `server/models/`:
- YAMNet, TFLite version, plus its class map:
  https://www.kaggle.com/models/google/yamnet/tfLite/classification-tflite.
  The class map is also at
  https://github.com/tensorflow/models/blob/master/research/audioset/yamnet/yamnet_class_map.csv.
- Porcupine: make a free account at https://console.picovoice.ai. Create a
  custom keyword for the demo name (Dara tells you the name by 6:30). Pick
  platform macOS and download the `.ppn`. Put the access key in `server/.env`
  as `PICOVOICE_KEY=`. Do not commit the key.

Steps:

1. 6:00. `main.py`, a FastAPI app. Allow all CORS origins; the Even WebView
   enforces CORS and the whitelist does not get around it. `WebSocket
   /ws/glasses` receives the section 3 frames, decodes `pcm` to int16, and
   appends to a rolling buffer. Every 0.5 s it calls the classifier, then the
   name spotter, then `state.update(...)`, and sends the result if it is not
   None. `POST /direction` stores the latest value with a timestamp. `GET /`
   is a status page. Add a `--mock` flag that skips audio and cycles idle,
   cue(doorbell, right), speech(left), name(left), alarm(siren, behind) every
   5 s. Wendy needs `--mock` by 7 pm, so build that part first.
2. 6:45. `classify.py`. Load `yamnet.tflite` with `tf.lite.Interpreter`. Run
   the last 15600 samples as float32 in the range -1 to 1. Take the top 3
   classes. Map YAMNet's names to ours:

   | YAMNet class name contains | our label |
   |---|---|
   | Doorbell | doorbell |
   | Knock | knock |
   | Siren, Civil defense siren, Police car (siren), Ambulance (siren), Fire engine, fire truck (siren) | siren |
   | Smoke detector, smoke alarm, Fire alarm, Alarm | alarm |
   | Vehicle horn, car horn, honking | horn |
   | Dog, Bark | dog |
   | Speech, Conversation, Narration, monologue | speech |

   Threshold 0.3 for cue classes and 0.5 for speech. Emit `Event(kind="sound",
   ...)` or `Event(kind="speech", speaker=<speakerRole from the frame>)`. Log
   every top 3 with scores, because we will tune thresholds from the log.
3. 7:30. `--wav path` flag. Play a 16 kHz mono WAV through the same buffer at
   normal speed and print the events. Get doorbell and siren right before
   anything else.
4. 8:30. `name.py`. Run Porcupine on the same int16 stream in frames of 512
   samples. Emit `Event(kind="name")` on a hit.
5. 9:30. Run live with Wendy's plugin on the real glasses and Dara's
   `state.py` plugged in. Tune thresholds in the hall noise using the table
   from Dara's `eval.py`.

Done when: with the real glasses, a doorbell played from a phone gives a
`sound/doorbell` event within 1 s, a siren gives `sound/siren`, a knock gives
`sound/knock`, the name gives `name`, and 30 s of hallway noise gives nothing
above threshold.

If stuck: if TensorFlow will not install, `pip install ai-edge-litert` gives
the same `Interpreter`. If YAMNet misses knocks on the glasses stream, ask
Wendy to switch the plugin to `AudioInputSource.Phone`; it is one argument.
If Porcupine is still fighting you at 9:30, drop the name feature and tell
Dara.

### 4.3 Iurii: direction hardware and the demo rig (`firmware/`)

You own everything physical and the direction arrow. The arrow is phase 2. It
starts only if phase 1 is not waiting on anything.

If the ESP32 node happens, install Arduino IDE 2 and, in Boards Manager,
"esp32 by Espressif Systems". `WiFi.h`, `HTTPClient.h`, and `driver/i2s.h`
come with it.

Steps:

1. 5:30, with Dara. The direction test. Dara runs `record.py` with the plugin
   on the real glasses. You stand 1 m away and talk for 5 s from the left,
   then the right, then the front, then behind, saying which position you
   are in. Dara writes the numbers in `docs/direction-test.md`. If the
   numbers separate by position, Tier 0 works and no hardware is needed. If
   they are always null or random, go to step 2.
2. 6:00. The MLH hardware table, if there is one. Ask for, in this order: two
   I2S microphone modules (INMP441, SPH0645, or ICS-43434); failing that, two
   analog microphone or sound modules (KY-038, KY-037, or MAX4466); ten male
   to female jumper wires; a USB data cable that fits the ESP32. If there are
   no microphones, there is no ESP32 node. Skip to step 5.
3. 6:30. Wire it. Two mics 15 cm apart on a strip of cardboard that sits on a
   cap, one over each ear. I2S: share SCK and WS, each SD to an I2S pin, tie
   the L/R select pins opposite. Analog: outputs to GPIO 34 and 35, plus 3.3 V
   and ground.
4. 7:30. Firmware in `firmware/direction/direction.ino`. Join the hotspot in
   `setup()`. Every 100 ms, read both mics, compute the RMS of each, and
   `margin_db = 20 * log10(rms_left / rms_right)`. If the absolute value is
   over 6, POST `{"dir":"left" or "right","margin_db":x}` to
   `http://LAPTOP_IP:8000/direction`. Blink the LED on every POST so you can
   see it is alive.
5. 8:00. The demo rig. Put the clips from section 6 on a phone. Get a
   Bluetooth speaker; a phone speaker is too quiet in the hall. Tape L and R
   on the table. Find a cap for the mic strip.
6. 8:30. Bench test with Nikhil's server log open. Talk from the left and the
   right. The log must show the correct side 9 times out of 10 at 1 m. Write
   the number in `docs/direction-test.md`.
7. 9:00. Cutoff. If it is not working, unplug it and help Nikhil tune
   thresholds. The product does not change.

Done when: `docs/direction-test.md` says one of three things. Tier 0 works and
here are the thresholds. The ESP32 gives the correct side 9 of 10. Or: no
direction, cut at 9 pm.

### 4.4 Dara: state machine, eval tools, glasses, submission (`server/state.py`, `tools/`)

Two pieces of code, plus the things that only you can do because they need
your phone and your accounts.

Setup:
```bash
cd ~/Projects/lahacks && mkdir -p tools server/clips
python3.12 -m venv .venv && source .venv/bin/activate
pip install fastapi "uvicorn[standard]" websockets numpy soundfile
npm i -g @evenrealities/evenhub-cli
```
Even app 2.2.10 or newer, signed in. Developer access turned on at
https://evenhub.evenrealities.com, then fully quit and reopen the phone app.
Phone auto lock set to Never. A Devpost project with all four of you and the
challenges Even Realities, Beyond the Digital, and Applied Intelligence.

Code:

1. 5:20. `tools/record.py`. A small WebSocket server on port 8000 that accepts
   the plugin's frames and writes `--out file.wav` (16 kHz mono) plus
   `file.jsonl` with one line per frame: `ts`, `direction`, `speakerRole`,
   RMS. Print the direction value live so the 5:30 test is just watching the
   terminal. Point Wendy's plugin at your laptop for this.
2. 5:30. The direction test with Iurii (his step 1). Then record 30 s each of
   silence, a doorbell clip, a siren clip, and knocks. Write
   `docs/direction-test.md`: a table of position against the `direction`
   values you saw, and the verdict. Give the WAVs to Nikhil.
3. 6:30. `server/state.py`, the function described in section 3. Rules:
   - alarm or siren gives `alarm`. It holds until 2 s after the last
     detection and suppresses everything else.
   - name gives `name` for 4 s. It beats speech and cue.
   - any other cue gives `cue` for 4 s. A newer cue replaces an older one.
   - speech with `speaker != "self"` gives `speech`. It holds while detected,
     fades 3 s after, and stays at least 1 s.
   - otherwise `idle`.
   - `dir` is the most recent `Direction` that is under 1 s old, else `near`.
   - return `None` when nothing changed, so the plugin is not spammed.
   Write `server/test_state.py` with plain asserts for: two sounds at once,
   alarm then doorbell, speech from self, direction expiring. Run it with
   `python server/test_state.py`.
4. 7:30. `tools/eval.py`. For every WAV in `server/clips/`, run Nikhil's
   `classify.py` over it in 0.5 s steps. Print the expected label (from the
   file name), the top label, the top score, and the time to the first
   correct label. Then print a confusion table. This gives the numbers for
   the pitch and is how we tune thresholds.
5. 9:00. Direction mapping. If Tier 0 works, write
   `direction_from_tag(int) -> "left" | "right" | "front" | "behind"` in
   `state.py` from your test table. Otherwise use the ESP32's `/direction`.
   Otherwise `near`.

Logistics, fitted in between. None takes more than 20 minutes:

6. 6:00. The Even table, which closes at 8 pm. Ask: does
   `AudioEvent.direction` carry data on current firmware, and in what unit?
   Confirm the Beta group flow. Ask whether "sound awareness for deaf users"
   counts as medical. It should not, but hear them say it.
7. 6:30. Pick the demo name with the team. Tell Nikhil so he can train the
   keyword.
8. 8:00. A throwaway package of Wendy's `?demo=1` build: `npm run build &&
   npx evenhub pack app.json dist -o earshot.ehpk`. In the portal, make a Beta
   group with your email, upload under Builds, push to the group. On the
   phone: Me, then Beta tester, then install. Whatever breaks here, fix it
   tonight rather than at 8 am.
9. 9:30. Integration on the real glasses. Run the full demo script. Film it
   even if it is rough; that is the backup video.
10. 11:00. Checkpoint. Either the loop worked once, or cut features in this
    order: name, direction, speech cue. Say which in the chat.
11. 12:30 am. Lock the phone 5 minutes and reopen. Deny the mic permission
    and check the app shows something sane. Double tap to exit.
12. 8:00 am. Final package and Beta push. Record the video, 2 to 3 minutes:
    20 s of pitch, the six demo steps, 20 s on how it works. Write the
    Devpost page; the skeleton can be done any time you are waiting on
    someone.
13. 10:00 am. Five rehearsals with someone who has not worn the glasses. Add
    the "Install and run on G2" section to the README. Even requires it.
14. 11:00 am. Submit Devpost. Confirm the Beta build is the final one. Nobody
    touches code after this.

Done when: `test_state.py` passes. `eval.py` prints a table with doorbell and
siren correct. `docs/direction-test.md` has a verdict. Devpost and the Even
Beta are both submitted by 11:30 am. The demo has run five times in a row with
nobody touching a laptop.

## 5. Checkpoints

| Time | Must be true |
|---|---|
| 7:00 pm | `--mock` works. The plugin shows mock states in the simulator. YAMNet labels a doorbell WAV. `state.py` tests pass. |
| 8:00 pm | Even table closes. A throwaway `.ehpk` has been installed from Beta. Mock states show on the real glasses. |
| 9:00 pm | Live audio from the glasses reaches the server. ESP32 cutoff. |
| 11:00 pm | The full loop has worked on the real glasses once. Cuts decided. |
| 2:00 am | Thresholds tuned in hall noise. Sleep. |
| 8:00 am | Final package, Beta push, video. |
| 11:00 am | Submitted. Code frozen. |

If the loop is not working at 11 pm, cut in this order: name flash, then
direction, then speech cue. Sound cue, alarm tier, and blank by default are
the product; those do not get cut.

## 6. Things to get tonight

Sound clips, on a phone (downloaded, not streamed) and as 16 kHz mono WAVs in
`server/clips/`, named by label, for example `doorbell_1.wav`. Convert with
`ffmpeg -i in.mp3 -ar 16000 -ac 1 out.wav`. Clips: doorbell 3 s, knock 2 s,
smoke alarm 5 s, siren 5 s, car horn 2 s, dog bark 2 s, and 30 s of hallway
noise as `noise_1.wav`. Iurii downloads, Dara converts.

Physical: a Bluetooth speaker, tape and a marker, everyone's chargers. A cap
only if the ESP32 node happens. From the MLH table, only if there is one: two
microphone modules, ten jumper wires, a USB data cable.

Accounts: Even developer access (Dara, before 6 pm). Picovoice and the `.ppn`
(Nikhil, by 8:30 pm). Devpost project (Dara, by 7 pm).

## 7. Submission checklist

- [ ] Devpost: description, track Beyond the Digital, challenges Even Realities and Applied Intelligence, public repo link, 2 to 3 minute video, "Built with" list, all four members.
- [ ] Even: the `.ehpk` on a Beta group and installed on Dara's phone. The Even Hub app name on the Devpost page. A README section "Install and run on G2" that lists any keys needed.
- [ ] Repo public. README has: what it is, the demo script, the diagram from section 2, how to run each piece, the contracts from section 3.
- [ ] Glasses, phone, laptop, and speaker charged. Auto lock off. Clips on the phone.
- [ ] One measured number for the pitch from `eval.py`: doorbell latency. Direction accuracy too, if we have it.
