# Devpost submission: Cue

What we submitted to https://la-ai-hackathon-2026.devpost.com/, kept as the
written story of the project. Numbers come from `PRD.md`,
`docs/eval-2026-10-17.md`, and `docs/direction-test.md`.

## 1. Name and tagline

**Project name:** Cue

**Tagline (58 chars):** Your G2 sees speech. With Cue, it sees everything else.

**Tracks / challenges:** Beyond the Digital; Even Realities Smart Glasses
Building Challenge; Applied Intelligence. Drop "Best Use of ElevenLabs":
the companion uses Android's own text-to-speech, not ElevenLabs. Entering it
would be false.

## 2. Story sections

### Inspiration

Even's G2 glasses already caption speech. Nothing on them, and nothing in
Even Hub's catalog of about 200 community apps, covers the sounds that are
not speech: the doorbell, the smoke alarm, the siren, a dog, a knock. A
phone app is too slow for those; by the time you look at it the sound is
over. Deaf and hard-of-hearing people told researchers that alarms are the
sound they most want (90%+ of 87 respondents, Bragg et al. 2016) and that a
head-mounted display is where they want it (75% of 201, Findlater et al.
2019). The gap was sitting on the judges' faces.

### What it does

The glasses stay blank. When a sound you cannot hear matters, one line
appears on the lens saying what it was and which side it came from:
`<-----  siren`, `dog bark  ----->`, `knock`. Then the display goes blank
again. Alarms and sirens take the whole display and hold until 3 s after
they stop. Someone else talking shows a quiet `speech` cue; the wearer's
own voice never triggers it. The wearer picks which sounds to see and a
tier for each (off, normal, medium, critical) with a tap on the glasses.
When you need to answer, the Android companion rings like a call, shows the
sound and three replies, and speaks the one you press, even with the phone
locked. "Please type it on my phone" opens a type-here page over the lock
screen.

### How we built it

Four devices on one hotspot, no cloud. The G2 streams 16 kHz PCM over
Bluetooth to the Even app, where our plugin (TypeScript in a WebView) sends
every 50 ms frame, plus the glasses' direction tag, over a WebSocket to a
FastAPI hub on a laptop. The hub fans each frame out unchanged over a
second WebSocket to an iPhone running YAMNet (TensorFlow Lite, 521 classes)
and gets the top 10 scores back every 0.5 s. The hub maps 27 YAMNet classes
to 9 labels, applies a threshold per label, requires 2 of the last 3
windows (2 of 4 for alarms), a cooldown, and a state machine with priority
alarm > cue > speech. A direction tracker turns the glasses' tag into left,
right, or center. The result is one state frame back to the plugin, which
draws one line in a single text container on the lens, at least 150 ms
between writes. The Android companion talks to the plugin on its own
WebSocket and is not in the sound path.

Four things we had to discover:

- The SDK's `AudioEvent.direction` is undocumented. We logged 322 frames,
  saw the values are `asin(k x 0.15)` for k = 0..6 plus 90, which is a
  two-mic time-difference estimate, and found the tag arrives one frame
  before the audio it describes. Pairing each frame's loudness with the
  previous frame's tag took the correct side from 4 of 10 to 8 of 10.
- The G2 audio stream is tuned for speech. On a real smoke alarm recorded
  through the glasses, 99.9% of the energy was below 500 Hz and raw YAMNet
  never scored alarm or siren above 0.08. A 600 Hz two-stage Butterworth
  high-pass plus gain normalization is the only reason alarms register.
- That same filter deletes knocks. Running YAMNet twice per window, filtered
  and raw, recovers them (13 to 19 of 22 clips). Measured, not shipped.
- Alarm holds 3 s and fires on 2 of 4 windows because the real recording
  has gaps up to 2.5 s between detections; 2 of 3 came on late and blinked.

### Challenges

The glasses' direction field had no unit, range, or documentation. The audio
stream hid alarms under rumble. The hotspot handed the laptop an IPv6-only
address that rotates, so the hub listens on both stacks. The Even WebView
only connects to whitelisted origins, so every laptop IP change means a
repack. A long-press on the touchpad opens Even AI before any plugin sees
it, so the on-glasses menu opens with a tap. TensorFlow would not install on
the laptop, so the classifier moved to the iPhone.

### Accomplishments

Zero false cues on six noise clips under every setting. A real smoke alarm
through the glasses shows ALARM at 1.0 s and holds. Direction with no added
hardware. An on-glasses menu. A companion that rings, speaks, and takes
typed replies over the lock screen. All of it on a physical G2 from a Beta
group install.

### What we learned

Thresholds from studio clips do not transfer to a speech-tuned mic stream;
every number in `labels.py` was set from measured clips. One mic axis gives
left and right and nothing more. A 100 ms tick that broadcasts only on
change is enough; the Bluetooth link cannot take faster HUD writes anyway.

### What's next

Ship the two-pass classifier (19 of 22 measured). Record every sound class
through the G2, not studio clips. Name flash with a keyword spotter. Let the
wearer teach it their own sounds. Haptic tap on a watch for the critical
tier. Film end-to-end latency on the real glasses.

## 3. Built with

Even Realities G2; Even Hub SDK 0.0.16 (`@evenrealities/even_hub_sdk`);
TypeScript, Vite, evenhub-cli; Python, FastAPI, uvicorn, websockets;
YAMNet (TensorFlow Lite) on iOS, Swift, TFLite Task Library,
`URLSessionWebSocketTask`; Kotlin, Android 13+ (targetSdk 37),
Java-WebSocket 1.6.0, Android TextToSpeech; ai-edge-litert and numpy for the laptop eval; WebSockets, JSON.

## 4. Even Realities challenge paragraph

Who uses this and when: deaf and hard-of-hearing people, at home and on the
street, whenever a sound they cannot hear matters. Why G2: it already sits
in their line of sight, it already captions speech, its two mics already
emit a direction tag, and it has no speaker, which costs a deaf user nothing.
Cue is an Even Hub app, not a device. Can I try it right now: yes. It is
installed from a Beta group on the phone the G2 is paired to. Put the
glasses on; nothing to set up. Tap the touchpad to open the sound menu,
swipe to a sound, tap to set its tier, tap DONE. Double-tap exits. Alarm and
siren are always on. App name on Even Hub: Cue.

## 5. Numbers

| figure | source | caveat |
|---|---|---|
| 0 false cues on 6 noise clips (vacuum, crying baby) | docs/eval-2026-10-17.md | every setting |
| alarm 4/4, siren 3/3, dog 3/3 | eval, shipped 600 Hz pipeline | studio clips except one real alarm |
| 13/22 clips, shipped | eval, "server today" row | doorbell 2/6, knock 0/3, horn 1/3 |
| 19/22 with filtered + raw | eval, `--dual` | measured, not shipped (PRD Sun 09:00) |
| 1.0 s median clip start to HUD: alarm, siren, knock, horn | eval | classifier on saved clips, not end to end; dog 2.5 s, doorbell 3.2 s |
| direction 8 of 10 at 1 m (left 4/5, right 4/5) | docs/direction-test.md | front and behind not separable; behind read wrong 2/3 |
| 322 frames, zero null tags | docs/direction-test.md | one real alarm recording |

## 6. Problem numbers with citations

- 1.5 billion people live with hearing loss; 430 million have disabling
  loss. WHO, World Report on Hearing, 2021.
- About 50% of deaf and hard-of-hearing respondents miss sounds more than
  once a day; emergency alarms ranked first at home (90%+). Bragg, Huynh,
  Ladner, "A Personalizable Mobile Sound Detector App Design for Deaf and
  Hard-of-Hearing Users," ASSETS 2016, n=87.
- 75% want visual alerts on a head-mounted display with haptics on a watch.
  Findlater et al., "Deaf and Hard-of-hearing Individuals' Preferences for
  Wearable and Mobile Sound Awareness Technologies," CHI 2019, n=201.
- About 200 apps in the Even Hub community catalog, none for non-speech
  sound. docs/RESEARCH.md, github.com/pangoleen/awesome-even-realities-g2.

## 7. Team

- Dara Miao (USC): evals (`tools/eval.py`, `dirtest.py`), direction
  mapping, state machine spec, docs, deck, submission.
- Iurii Kolyadin (UC Irvine): Android companion (`android-companion/`).
- Nikhil Marisetty (UT Dallas): hub (`server/`), iPhone classifier
  (`audio_classification/`).
- Wendy Wang (UCLA): Even Hub plugin (`plugin/`), on-glasses menu.

## 8. Video shot list, 2:30

| t | shot | on screen |
|---|---|---|
| 0:00 | Judge's view, lens blank | title card: Your G2 sees speech. With Cue, it sees everything else. |
| 0:05 | Dara to camera, 15 s | the problem in one breath: deaf people miss the siren, no glasses app shows it |
| 0:20 | Through-lens, siren clip from the right | `SIREN  ----->` full screen, held, then blank |
| 0:35 | Through-lens, dog bark from the left | `<-----  dog bark` 4 s, blank |
| 0:45 | Teammate claps on the right | `clapping  ----->` 4 s, blank |
| 0:55 | Phone on the table, locked, siren again | phone rings like a call, lock screen shows siren and three replies |
| 1:10 | Judge taps a reply | phone speaks "Sorry, could you repeat that while facing me?" |
| 1:20 | Tap the touchpad | on-glasses menu: swipe, tap to cycle a tier, DONE |
| 1:35 | Hand the glasses to the next person | nothing to set up |
| 1:45 | Architecture, 20 s | the four-device drawing from the deck; say the direction tag and the 600 Hz finding |
| 2:05 | Numbers card | 0 false cues, 8 of 10 sides, alarm at 1.0 s |
| 2:15 | Close | Put the glasses on. Repo URL. |

The PRD demo is siren, dog bark, clap (three sounds that detect every time
through the glasses), not six beats. The PLAN's six-step script predates
the Sun 09:15 decision.
