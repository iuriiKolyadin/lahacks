# Earshot

Sound awareness for deaf and hard-of-hearing people, on Even Realities G2
smart glasses. The glasses stay blank. When a sound you cannot hear matters,
a doorbell, a knock, a siren, an alarm, one line appears in your line of
sight saying what it was and which side it came from. Then the display goes
blank again.

Built in 24 hours at LA Hacks AI Hackathon, UCLA, 17 to 18 October 2026, for
the Beyond the Digital track and the Even Realities challenge.

## Why

Even's G2 already captions speech with its built-in Conversate mode. Nothing
on the glasses handles the sounds that are not speech, and a phone is too
slow: by the time you look at it, the sound is over. Earshot covers
everything Conversate ignores, with no external hardware. The G2 has no
speaker, which costs a deaf user nothing.

## What it detects

Doorbell, knock, siren, alarm, car horn, dog bark, clap, snap, and someone
else speaking. Alarms and sirens take the whole display. Direction comes
from the glasses' own microphone array: left and right, with front and behind
drawn as "center" because the glasses cannot tell them apart.

## How it works

```
 G2 glasses ──Bluetooth──▶ Even app running plugin/ ──WebSocket──▶ server/ (laptop hub)
                            forwards audio, draws the HUD                 │
                                     ▲                                    ▼
                                     └──── HUD state ◀──── audio_classification/ (phone, YAMNet)
```

| folder | what | owner |
|---|---|---|
| `plugin/` | the Even Hub app: streams glasses audio up, draws one line on the lenses | Wendy |
| `server/` | the hub: YAMNet label map, thresholds, direction from the G2 tag, the state machine, mock mode | Nikhil, state machine spec by Dara |
| `audio_classification/` | TensorFlow Lite audio example with `EarshotLink.swift`: runs YAMNet on a phone and returns scores to the hub | Nikhil |
| `tools/` | `eval.py` scores the pipeline on saved clips; `dirtest.py` analyses the direction tag | Dara |
| `docs/` | research, eval results, direction findings | |

Read `PRD.md` for the full record: problem, design, measurements, every
decision and why.

## Run it

Three things on one Wi-Fi network (a phone hotspot; venue Wi-Fi usually
blocks phone-to-laptop traffic).

1. Hub, on a laptop:
   ```bash
   cd server && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
   .venv/bin/python main.py          # prints the addresses to point the other two at
   .venv/bin/python main.py --mock   # cycles every HUD state with no audio, for plugin work
   ```
2. Classifier, on an iPhone: open
   `audio_classification/ios/AudioClassification.xcworkspace`, run it, tap
   the status text, enter `ws://LAPTOP_IP:8000/ws/classifier`, choose "Use
   glasses audio". Without a phone, `server/fake_classifier.py --model
   ../audio_classification/ios/AudioClassification/TFLite/yamnet.tflite`
   runs the same model on the laptop.
3. Glasses app:
   ```bash
   cd plugin && npm install
   # put the hub's http:// and ws:// origins in app.json under permissions → network → whitelist
   npm run dev                                   # then, on the phone, scan:
   npx evenhub qr --url http://LAPTOP_IP:5173
   ```
   To install as a Beta build: `npm run build && npx evenhub pack app.json dist -o earshot.ehpk`,
   upload at https://evenhub.evenrealities.com to a Beta group containing
   your Even account email, then on the phone: Me, Beta tester, install.
   The app needs the `g2-microphone` permission and nothing else; no keys.

Measure it: `python3 -m venv .venv && .venv/bin/pip install numpy ai-edge-litert && .venv/bin/python tools/eval.py --dual`.

## Results

22 test clips through the shipped pipeline: alarm 4/4, siren 3/3, dog 3/3,
and zero false cues on 6 noise clips. Knocks and most doorbells are lost to
the high-pass filter that alarms need; a measured two-path fix gets 19 of 22
but was not shipped. About 1 s from sound to HUD state for alarms and
sirens. Direction correct 8 of 10 at 1 m. Details and caveats in
`docs/eval-2026-10-17.md` and `docs/direction-test.md`.

## Team

Dara Miao (USC), Iurii Kolyadin (UC Irvine), Nikhil Marisetty (UT Dallas),
Wendy Wang (UCLA).
