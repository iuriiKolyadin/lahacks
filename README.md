# Earshot

Sound awareness for deaf and hard-of-hearing people, on Even Realities G2
smart glasses. The glasses stay blank. When a sound you cannot hear matters,
a doorbell, a knock, a siren, an alarm, or your own name, one line appears in
your line of sight saying what it was and which way it came from.

Built at the LA Hacks AI Hackathon, 17 to 18 October 2026, for the Beyond the
Digital track and the Even Realities challenge.

## Read these

- `PRD.md`: what we are building and why, the demo script, requirements.
- `PLAN.md`: how it is built, who builds what, message formats, checkpoints.
- `docs/RESEARCH.md`: what Even Realities has, what the SDK gives us, prior
  art, and what Earshot adds.

## Layout

| Folder | What | Owner |
|---|---|---|
| `plugin/` | the Even Hub app that runs on the phone and draws on the glasses | Wendy |
| `server/` | Python hub: relays glasses audio to the iPhone classifier, turns its scores into HUD states, estimates direction | Nikhil |
| `audio_classification/ios/` | iPhone app that runs YAMNet on the glasses audio and sends the scores back | Nikhil |
| `tools/` | recording and evaluation scripts | Dara |
| `docs/` | research and test results | everyone |

## Run it

How the pieces talk:

```
G2 glasses --Bluetooth--> glasses phone (Even app + Earshot plugin)
                                  |  ws://SERVER:8000/ws/glasses   (audio up, HUD states down)
                                  v
                          server laptop (server/main.py)
                                  |  ws://[SERVER_IPV6]:8000/ws/classifier   (audio out, scores back)
                                  v
                          classifier iPhone (AudioClassification app, YAMNet)
```

Four devices, all on one hotspot:

| Device | Who | Runs |
|---|---|---|
| Glasses phone | whoever the G2 is paired to | Even app, hosts the hotspot, loads the plugin |
| Server laptop (Windows in our setup) | same person | `server/main.py` and the plugin dev server |
| Classifier iPhone | Nikhil | the iOS classifier app |
| Mac | Nikhil | Xcode, only to install or update the iOS app |

The steps below start from everything switched off. Do them in order.

### 1. One-time setup (skip if already done)

Server laptop, in a terminal:

```
git clone https://github.com/iuriiKolyadin/lahacks.git
cd lahacks\server
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
cd ..\plugin
npm install
```

(On a Mac use `python3` and `.venv/bin/...` instead of `.venv\Scripts\...`.)

Server laptop, Windows firewall: open Command Prompt **as administrator**
(Start, type `cmd`, right-click, Run as administrator) and run:

```
netsh advfirewall firewall add rule name="Earshot 8000" dir=in action=allow protocol=TCP localport=8000
netsh advfirewall firewall add rule name="Earshot 5173" dir=in action=allow protocol=TCP localport=5173
```

Both should print `Ok.` This opens the server port and the plugin dev port on
every network type. Allowing `python.exe` in Windows Security is not enough:
the venv's `python.exe` is a launcher, so the rule can end up on the wrong
program. If a Windows prompt was ever cancelled, delete any red "block" rule
for Python under Windows Security, Firewall & network protection, Advanced
settings, Inbound Rules; block rules beat allow rules. Remove these later with
`netsh advfirewall firewall delete rule name="Earshot 8000"` (and `5173`).

Mac, to install the classifier app on the iPhone (also how to update it):

1. Plug the iPhone into the Mac, unlock it, tap Trust.
2. If `audio_classification/ios/Pods/` is missing: `cd audio_classification/ios && pod install`.
3. Open `audio_classification/ios/AudioClassification.xcworkspace` (the
   `.xcworkspace`, not the `.xcodeproj`).
4. Pick the iPhone in the device menu at the top, press Run (Cmd+R).
5. If iOS blocks it: Settings, Privacy & Security, Developer Mode on; or
   Settings, General, VPN & Device Management, trust the developer profile.

### 2. Power on and join one network

1. Turn on the glasses phone. Settings, Personal Hotspot: turn on **Allow
   Others to Join** and **Maximize Compatibility** (2.4 GHz; many Windows
   laptops cannot see the hotspot without it). Keep this screen open while the
   others join; an iPhone stops advertising the hotspot when it locks.
2. Turn on the server laptop and join the hotspot.
3. Turn on the classifier iPhone and join the same hotspot.
4. Turn on the glasses and make sure they are connected in the Even app.

Do not use venue Wi-Fi: it usually blocks devices from reaching each other.

Our hotspot is on T-Mobile, which hands some devices **IPv6 only** (a Mac
shows the useless address `192.0.0.2`). The server listens on IPv4 and IPv6
at once; the iPhone app connects over IPv6, the plugin over IPv4. That is why
there are two addresses below.

### 3. Start the server (server laptop)

```
cd lahacks
git pull
cd server
.venv\Scripts\python main.py
```

It prints:

```
Earshot hub (live) on port 8000. Point the plugin and the iPhone at:
  ws://[2607:fb91:...]:8000/ws/glasses    ws://[2607:fb91:...]:8000/ws/classifier
Nothing more prints until something connects.
```

If it says the port is in use, an old server (often `plugin/fake_server.py`)
is still running: close it, or find it with `netstat -ano | findstr :8000` and
`taskkill /PID <pid> /F`.

Find the server laptop's two addresses with `ipconfig` (Mac: `ifconfig`):

- **IPv4 Address**, for example `172.20.10.3`. The plugin uses this.
- **IPv6 Address** starting `2607:` (not "Temporary IPv6 Address", not the
  `fe80::` link-local one). The iPhone app uses this.

Check from the classifier iPhone: open `http://[THE_IPV6]:8000/` in Safari,
brackets included. You should see JSON starting `{"mode":"live"`. If it hangs,
it is the firewall (step 1) or the two devices are on different networks.

### 4. Connect the classifier iPhone

1. Open the **AudioClassification** app (our modified TensorFlow Lite
   example). Allow local
   network access the first time it asks.
2. Tap the status text at the top of the results list.
3. Enter `ws://[THE_IPV6]:8000/ws/classifier`, square brackets included.
4. Tap **Use glasses audio**.
5. The status shows **Connected**. The server console prints
   `classifier connected`. Leave the app open, screen on, plugged in; the
   socket drops if the app goes to the background.

The app remembers the address. It only changes if the server laptop rejoins
the hotspot and gets a new IPv6 address.

**Use phone mic** in the same menu makes the iPhone listen with its own
microphone instead of the glasses (no direction arrows, and the wearer's own
voice counts as speech). Use it only if the glasses audio is not working.

### 5. Load the plugin on the glasses phone

On the server laptop, in a second terminal (keep `main.py` running):

```
cd lahacks\plugin
npm run dev
```

Vite prints a `Network:` line such as `http://172.20.10.3:5173/`. In a third
terminal:

```
cd lahacks\plugin
npx evenhub qr --url http://THE_IPV4:5173
```

Scan the QR code with the Even app on the glasses phone. The Earshot page
opens. Check:

- The status chip says **Connected · ws://THE_IPV4:8000/ws/glasses**.
- The Mic line counts frames, for example `17 frames/s · rms ...`.
- The server console prints `glasses connected`, then a `TIER0` line every
  second and `RESULT` lines from the iPhone about twice a second.

If the plugin page shows the Even Hub store instead, it is not loaded: scan
the QR again. If the chip says **Demo mode**, remove `?demo=1` from the URL.
To check the HUD layouts without the server, load
`http://THE_IPV4:5173/?demo=1`.

### 6. Test it

Wear the glasses and make sounds about 1 m away. What shows:

| Sound | HUD | Needs |
|---|---|---|
| Smoke alarm, fire alarm | `ALARM` | score 0.3 in 2 of the last 4 half-second windows; holds 3 s after the sound stops |
| Siren | `SIREN` | same as alarm |
| Doorbell, knock, car horn | the word | score 0.5 in 2 of the last 3 windows (about 1 s of sound) |
| Dog barking | `dog bark` | score 0.4 in any one window (a bark is short) |
| Clapping, finger snapping | `clapping`, `snap` | same as above; a single snap may not count |
| Someone else talking | `speech` | score 0.6 in 2 of 3; the wearer's own voice is ignored |

Anything else (water, hum, music, room noise) shows nothing, on purpose. The
classifier iPhone shows its raw guesses for every sound; only the ones above
reach the glasses. YouTube clips played from a phone work for doorbells,
sirens and alarms.

Direction arrows:

| Sound from | HUD |
|---|---|
| left | `<-----  KNOCK` |
| right | `KNOCK  ----->` |
| ahead or behind | `^ | |` above the word and `| | v` below it |

The glasses measure one left-right angle from two microphones, so a sound
straight ahead and one straight behind read the same; the double arrow means
"ahead or behind you." Anything within 25 degrees of center counts as center.
Tune in `server/direction.py` (`SIDE_DEG`, `SIGN`); the server's `TIER0` line
shows the live angle.

### 7. Alert levels

On the plugin page on the glasses phone, each sound has a **Critical /
Medium / Normal** picker:

| Level | On the glasses |
|---|---|
| Critical | `K N O C K` spaced capitals (between `=====` bars when there is no up/down arrow), fast deep flashing |
| Medium | `KNOCK` capitals, slower shallower flashing |
| Normal | `knock` lowercase, dimmer, two blinks then steady |

Alarm and siren are locked to Critical. The glasses have one fixed font, so
"bigger" is spacing and the frame, not font size. Choices are saved on the
glasses phone.

### 8. Tuning

All on the server laptop; restart `main.py` after editing.

- `server/labels.py`: which YAMNet classes map to which sound, the score
  `THRESHOLD` per sound, `HITS` (how many recent windows must pass), and
  `COOLDOWN_S` (how soon the same sound can show again).
- `server/state.py`: how long cues, alarms and speech stay up.
- `server/direction.py`: left/right sign and the center zone.

Without the glasses or the iPhone, from `server/`:

```
python fake_classifier.py                       # stands in for the iPhone (scripted)
python fake_glasses.py --wav clip.wav           # stands in for the plugin
python fake_glasses.py --wav ../plugin/recordings/alarm_1.wav --jsonl ../plugin/recordings/alarm_1.jsonl
python test_state.py                            # state machine tests
```

`fake_classifier.py --model ../audio_classification/ios/AudioClassification/TFLite/yamnet.tflite`
runs the same model and preprocessing as the iPhone (needs
`pip install -r requirements-model.txt`). See `server/README.md`.

### 9. When something does not work

| Symptom | Cause and fix |
|---|---|
| Server console: port 8000 in use | Another server is running. Close it or `taskkill` it (step 3). |
| Safari on the iPhone hangs on `http://[IPv6]:8000/` | Firewall rule missing (step 1), or the iPhone is not on the hotspot. |
| iPhone app: Disconnected, retrying | Wrong address, or the server laptop's IPv6 changed. Run `ipconfig` again and re-enter it. |
| Server status shows `glasses: 0` | The plugin is not loaded or not connected. Look at the plugin's status chip (step 5). |
| Plugin: Disconnected, retrying · ws://...:8000 | It loaded from an address the server is not reachable on. Reload with `?server=ws://THE_IPV4:8000/ws/glasses`. |
| Server laptop cannot see the hotspot | Maximize Compatibility off, or the hotspot screen locked (step 2). |
| Sounds show nothing | Check that the sound is in the table in step 6, and that `RESULT` lines are printing. The phone's raw guesses show what the model heard. |
| Arrows point the wrong way | Flip `SIGN` in `server/direction.py`. |

Live status from any device on the hotspot: `http://[THE_IPV6]:8000/`
(`glasses`, `classifiers`, `audio_frames`, `results`, current `state`,
`direction_deg`).

### 10. Shut down

1. Plugin: double-tap the glasses temple and confirm exit.
2. Server laptop: Ctrl+C in each terminal (`main.py`, `npm run dev`).
3. Classifier iPhone: close the app.
4. Turn off the hotspot last.

## Install and run on G2

Filled in before submission. Will cover: packaging with `evenhub pack`,
the Beta group, the network whitelist, and the one key needed
(`PICOVOICE_KEY` for the name spotter).
