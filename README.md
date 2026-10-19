# Cue

**Your G2 already sees speech. With Cue, it sees everything else.**

[![Cue on Even G2: the lens reads <----- siren](docs/deck/images/title.jpg)](https://youtu.be/71S9_XT-4Dg)

Sound awareness for deaf and hard-of-hearing people, on Even Realities G2
smart glasses. The glasses stay blank until a sound you cannot hear matters;
then one line in your line of sight says what it was and which side it came
from. [Two-minute demo on a real G2.](https://youtu.be/71S9_XT-4Dg)

A phone is too slow for this: by the time you take it out, the sound is over.
The G2 is already where you are looking, and Even's built-in Conversate mode
already captions speech, but nothing on the glasses says that a doorbell rang
or which side a voice came from. Cue does, with no hardware beyond the glasses
and a phone.

Built in 24 hours at LA Hacks AI Hackathon, UCLA, 17 to 18 October 2026, for
the Beyond the Digital track and the Even Realities challenge. The full record
(problem, design, measurements, every decision and why) is in [`PRD.md`](PRD.md).

## What it does

- Detects doorbell, knock, siren, alarm, car horn, dog bark, clap, and snap.
  Alarms and sirens take the whole display and hold until 3 s after the last
  detection, so a real alarm with gaps in it does not blink.
- Shows direction from the glasses' own microphone array: left or right.
  Front and behind read the same to the G2 and are drawn as "center".
- Captions anyone else who speaks, under the arrow for their side. The
  wearer's own voice is never captioned. Any sound replaces the captions.
- Lets the wearer choose, on the glasses, which sounds to see and how loudly
  each alerts: tap the touchpad for the menu, swipe to a sound, tap to cycle
  off / normal / medium / critical, tap DONE. Alarm and siren are always on.
- Rings the wearer's Android phone like an incoming call for critical and
  medium sounds, with the sound, its direction, and one button per reply.
  A reply is spoken aloud; "please type" opens a page over the lock screen
  for the other person to type on.

## How it works

![Four devices, one hotspot: glasses, Even app, laptop hub, iPhone classifier](docs/deck/images/architecture.jpg)

Nothing leaves the hotspot. The glasses stream 16 kHz audio to the Even app,
the plugin forwards every 50 ms frame plus the glasses' direction tag to a
FastAPI hub on a laptop, the hub fans the audio out to an iPhone running
YAMNet and gets scores back every 0.5 s, and a state machine (alarm > cue >
speech) sends one HUD frame back to the lens. The Android companion hangs off
the plugin and is not in the sound path.

Two findings made it work. The SDK's undocumented direction tag arrives one
frame before the audio it describes; pairing each frame with the previous tag
took the correct side from 4 of 10 to 8 of 10. And the G2 audio stream is
tuned for speech, so a real smoke alarm arrives almost entirely below 500 Hz
and YAMNet never sees it; a 600 Hz high-pass runs first. The rest is in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

| folder | what |
|---|---|
| [`plugin/`](plugin/) | the Even Hub app: streams glasses audio up, draws one line on the lenses, the on-glasses menu |
| [`server/`](server/) | the hub: YAMNet label map and thresholds, direction from the G2 tag, the state machine, live captions, mock mode |
| [`audio_classification/`](audio_classification/) | TensorFlow Lite audio example plus `EarshotLink.swift`: runs YAMNet on an iPhone, returns scores to the hub |
| [`android-companion/`](android-companion/) | rings like a call on urgent sounds, speaks replies, type-here page over the lock screen |
| [`tools/`](tools/) | `eval.py` scores the pipeline on saved clips; `dirtest.py` reads the direction tag at each snap |
| [`docs/`](docs/) | architecture, glasses-to-phone protocol, research, eval and direction results, deck copy |

## Run it

Everything on one Wi-Fi network. Use a phone hotspot; venue Wi-Fi usually
blocks phone-to-laptop traffic.

1. **Hub**, on a laptop. Prints the addresses the other pieces connect to.
   ```bash
   cd server
   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
   .venv/bin/python main.py --stt whisper      # offline captions, 1 to 2 s behind; first run downloads the model
   # or: DEEPGRAM_API_KEY=... .venv/bin/python main.py --stt deepgram   (about 0.5 s behind, needs internet)
   # or: .venv/bin/python main.py --mock       (cycles every HUD state, no audio; for plugin work)
   ```
2. **Classifier**, on an iPhone. Open
   `audio_classification/ios/AudioClassification.xcworkspace`, run it, tap the
   status text, enter `ws://LAPTOP_IP:8000/ws/classifier`, choose "Use glasses
   audio". No iPhone? `server/fake_classifier.py --model ../audio_classification/ios/AudioClassification/TFLite/yamnet.tflite`
   runs the same model on the laptop.
3. **Glasses app.** Set the whitelist in `plugin/app.json` to the hub's exact
   `http://` and `ws://` origins, then either run it in development or install
   it on the G2. It needs only the `g2-microphone` and `network` permissions.
   ```bash
   cd plugin && npm install
   npm run dev && npx evenhub qr --url http://LAPTOP_IP:5173            # dev: scan from the Even app
   npm run build && npx evenhub pack app.json dist -o cue.ehpk          # install: upload at evenhub.evenrealities.com
   ```
   For the install, add the `.ehpk` to a Beta group containing your Even
   account email, then on the phone: Me, Beta tester, install.
4. **Companion**, on an Android phone. Build per
   [`android-companion/README.md`](android-companion/README.md), then in the
   app: Connection, `ws://LAPTOP_IP:8000/ws/pendant`, Apply.

To measure instead of run: `python3 -m venv .venv && .venv/bin/pip install numpy ai-edge-litert && .venv/bin/python tools/eval.py`.

## Results

| | |
|---|---|
| Detection, 22 test clips | alarm 4/4, siren 3/3, dog 3/3, zero false cues on 6 noise clips |
| Clip start to HUD state, classifier time on saved clips | 1.0 s for alarms and sirens |
| Direction, 16 snaps at 1 m | correct side 8 of 10 |

The 1.0 s excludes the Bluetooth and WebSocket hops; end-to-end latency on
the glasses was not filmed. Knocks and most doorbells are lost to the
high-pass filter that alarms need. Running YAMNet on both the filtered and
raw audio recovers them (19 of 22), measured but not shipped. Details and
caveats in [`docs/eval-2026-10-17.md`](docs/eval-2026-10-17.md) and
[`docs/direction-test.md`](docs/direction-test.md).

Next: ship the two-pass classifier, re-record every sound class through the
G2 instead of studio clips, flash the wearer's name with a keyword spotter.

## Deck

![Deaf people miss a sound every day; no glasses app shows one](docs/deck/images/problem.jpg)

![When you need to answer, the phone does the talking](docs/deck/images/companion.jpg)

Slide copy and brand notes in [`docs/deck/`](docs/deck/).

## Team

- [Dara Miao](https://github.com/dara-miao), USC: evals, direction mapping, state machine spec, docs, deck.
- [Iurii Kolyadin](https://github.com/iuriiKolyadin), UC Irvine: Android companion.
- [Nikhil Marisetty](https://github.com/sainikhil1611), UT Dallas: hub and iPhone classifier.
- [Wendy Wang](https://github.com/Ruiyang1210W), UCLA: Even Hub plugin and on-glasses menu.

## License

MIT. Test clips in `server/clips/` keep their own licenses, listed in
[`server/clips/SOURCES.md`](server/clips/SOURCES.md). The project was called
Earshot for most of the hackathon; code identifiers kept that name.
