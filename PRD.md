# Cue: product and build record

(Called Earshot until Sunday morning; code identifiers still say `earshot`.)

Built at LA Hacks AI Hackathon, UCLA, 17 to 18 October 2026, for the Beyond
the Digital track and the Even Realities challenge. Team: Dara Miao, Iurii
Kolyadin, Nikhil Marisetty, Wendy Wang.

This is the one document: what we set out to build, what we built, what we
measured, and what we decided along the way. Background research is in
`docs/RESEARCH.md`; measurements are in `docs/eval-2026-10-17.md` and
`docs/direction-test.md`; the sound path in detail is `docs/ARCHITECTURE.md`;
the glasses-to-phone protocol is `docs/BRIDGE.md`.

## 1. The problem

Deaf and hard-of-hearing people miss the sounds that are not speech: a
doorbell, a knock, a siren, a smoke alarm, their own name from across a room.
Phone apps exist for some of this, but by the time you take the phone out and
look, the sound is over. Even's G2 glasses already caption speech with the
built-in Conversate mode. Nothing on the glasses, and nothing in Even Hub's
catalog of about 200 community apps, handles the sounds that are not speech.

## 2. What Cue does

The glasses stay blank. When a sound you cannot hear matters, one line
appears in your line of sight saying what it was and which side it came
from, then the display goes blank again.

- Sounds: doorbell, knock, siren, alarm, car horn, dog bark, plus clap and
  snap for demos in a loud hall.
- Alarms and sirens take the whole display at full brightness and suppress
  everything else until they stop.
- Someone else talking shows a quiet "speech" cue with a side. The wearer's
  own voice never triggers it; the SDK tells us which frames are the wearer.
- Direction comes from the glasses themselves. Left and right work. Front
  and behind cannot be told apart and are drawn as "center".
- The wearer picks which sounds to see and an alert tier for each (off,
  normal, medium, critical), on the glasses (long-press opens the menu, swipe
  moves, tap cycles, long-press or DONE saves, double-tap cancels) or on the
  phone page. Alarm and siren are locked on at critical.
- An Android companion app answers for the wearer. When the glasses flash a
  critical or medium sound, the phone rings like an incoming call and shows
  the sound, its direction, and one button per reply. A button speaks the
  reply out loud through the phone speaker ("Sorry, could you repeat that
  while facing me?"), and "please type" wakes the phone with an "I'm Deaf.
  Please type here" page over the lock screen. The G2 has no speaker, so the
  phone is the voice.
- No captions, no transcription, no words shown, ever. Conversate does that.

## 3. Who it is for and why glasses

A deaf or hard-of-hearing adult who already wears the G2 through the day.
The cue has to arrive the instant the sound does, in their line of sight,
hands free. The G2 has no speaker, which costs a deaf user nothing. Even's
own brief for the hackathon asked for "a small, timely cue in the wearer's
line of sight."

Pitch, one breath: a deaf person misses the doorbell, the siren, and their
own name. Conversate already captions what people say to you. Cue covers
everything Conversate ignores, and shows nothing the rest of the time.

## 4. The demo

Judge wears the G2. HUD is blank. A teammate:

| # | does | judge sees |
|---|---|---|
| 1 | plays a siren clip from a speaker on the right | full screen `SIREN` with `----->`, held while it plays, then blank |
| 2 | plays a dog bark on the left | `<-----  dog bark` for 4 s, then blank |
| 3 | claps once, standing on the right | `clapping  ----->` for 4 s, then blank |
| 4 | hands the glasses to the next judge | nothing to set up |

Three sounds that detect reliably through the glasses: siren 3 of 3 and dog
3 of 3 in the eval, and clap tuned live in the hall. The clap is the one a
judge can do themselves.

## 5. How it works

```
 G2 glasses ──Bluetooth──▶ phone: Even app running plugin/ ──WebSocket──▶ laptop: server/
   4 mics, 16 kHz PCM        sends every audio frame up                     hub + state machine
   + direction tag           draws whatever state comes down                       │
   + speakerRole                      ▲                                             ▼
                                      │                                   phone app: audio_classification/
                                      └──────────── HUD state ◀─────────  YAMNet, scores back to the hub
```

- `plugin/` (Wendy): the Even Hub app. A Vite and TypeScript page the Even
  app loads in a WebView. Forwards each audio event, with the glasses'
  `direction` and `speakerRole` fields, to the hub, and renders the state
  that comes back as one text container with ASCII arrows, three alert tiers,
  and flashing. Demo mode with `?demo=1`. Its fake server records what the
  glasses hear.
- `server/` (Nikhil, state machine spec by Dara): a FastAPI hub. Relays
  glasses audio to the classifier app and classifier scores back through
  `labels.py` (YAMNet class map, per-label thresholds, k-of-n hit rules,
  cooldowns), `direction.py` (the G2 tag to a side), and `state.py` (alarm
  beats name beats cue beats speech beats idle, with hold times). Mock mode
  and WAV replay so it runs without glasses. Tests in `test_state.py`.
- `audio_classification/` (Nikhil): the TensorFlow Lite audio classification
  example, with `CueLink.swift` added so the iOS build takes audio from
  the hub and returns YAMNet scores. Before the model: a 600 Hz high-pass
  and per-window gain, because the G2 stream is dominated by rumble under
  300 Hz and raw YAMNet hears "Music, Throbbing".
- `android-companion/` (Iurii): the phone half of "answer for me". The
  plugin sends an `alert` frame whenever the glasses are flashing a critical
  or medium sound; the hub relays it to the companion on `/ws/pendant`. The
  companion rings with a call-style notification, shows a full-screen page
  over the lock screen with the sound, its direction, and the reply buttons,
  speaks replies with on-device text to speech, and can show a type-here
  page. Protocol in `docs/BRIDGE.md`.
- `tools/` (Dara): `eval.py` scores the whole pipeline on saved clips;
  `dirtest.py` reads a server dump and shows what the direction tag did at
  each snap or knock.

Message formats, so the pieces could be built on separate laptops:

```
plugin → hub   {"t":"audio","pcm":"<base64 int16 LE 16 kHz mono>","direction":int|null,"speakerRole":"self|other|unknown","ts":ms}
hub → app      the same frame, unchanged
app → hub      {"t":"result","ts":ms,"inference_ms":n,"top":[{"label":"Doorbell","score":0.82},...]}
hub → plugin   {"state":"idle|cue|speech|name|alarm","label":"doorbell|knock|siren|alarm|horn|dog|clap|snap|speech","dir":"left|right|center|near","ttl_ms":n,"level":1..4}
plugin → hub → companion   {"v":1,"type":"alert","id":"a...","active":true,"label":"siren","text":"Siren","dir":"right","tier":"critical","ts":ms}
```

## 6. What we measured

Full tables in `docs/eval-2026-10-17.md` and `docs/direction-test.md`.

Classifier, 22 clips (6 doorbells from Wikimedia Commons, the rest ESC-50,
plus one smoke alarm recorded through the G2), scored by whether the HUD
would have shown the label:

| preprocessing | alarm | siren | doorbell | knock | horn | dog | false cues on 6 noise clips |
|---|---|---|---|---|---|---|---|
| raw audio | 2/4 | 2/3 | 3/6 | 3/3 | 2/3 | 3/3 | 0 |
| 600 Hz high-pass + gain (what ships) | 4/4 | 3/3 | 2/6 | 0/3 | 1/3 | 3/3 | 0 |
| both, max score per label | 4/4 | 3/3 | 4/6 | 3/3 | 2/3 | 3/3 | 0 |

Time from sound start to HUD state, classifier only: about 1 s for alarm,
siren, knock, horn; 2.5 s for dog; 3 s for doorbell (the second ring is what
crosses the 2-of-3 windows rule). The real smoke alarm through the G2 reaches
ALARM at 1.0 s with the high-pass and never fires without it.

Direction, 16 finger snaps at 1 m through the real glasses: correct side 8
of 10 for left and right. Front reads center 2 of 3. Behind reads wrong
more often than not; the glasses cannot tell front from behind.

## 7. What we deliberately did not build

- Captions or transcription. Conversate exists, the SDK has no speech
  recognition API, and Even's judges said caption apps will not stand out.
- Anything medical or emergency-routing. Even Hub bans these. We display
  sounds; we never call anyone.
- Name detection. Planned as a Picovoice keyword spotter; first on the cut
  list and cut at the 11 pm checkpoint.
- A phrase picker on the glasses themselves (swipe to choose, long-press to
  speak). The replies live on the companion phone's alert page instead; the
  glasses stay output-only.
- External microphones or an ESP32 direction node. Not needed once the
  glasses' own direction tag turned out to carry data.
- A camera. The G2 has none and the product does not need one.

## 8. Decisions, in order

| when | decision | why |
|---|---|---|
| Sat 15:00 | drop the robot arm we came with | no servos, no fasteners, no time |
| Sat 16:30 | drop CPR coaching and EMT tools | Even Hub bans medical and emergency-routing apps |
| Sat 17:00 | drop captions | Conversate does it; no STT in the SDK; Even says caption apps will not stand out |
| Sat 17:10 | everything runs on the G2 mic alone | the kit had no other microphone |
| Sat 19:20 | drop the ESP32 mic node; add a pendant speaker | the glasses' direction tag looked real; the G2 has no speaker |
| Sat 20:00 | classifier moves from the laptop to a phone app | TensorFlow would not install cleanly; the TFLite example runs YAMNet on device |
| Sat 22:00 | 600 Hz high-pass before YAMNet | raw G2 audio reads as rumble; a real alarm scored 0.3 to 0.5 after filtering, never before |
| Sat 23:00 | name flash cut | not started; everything else was closer |
| Sat 23:20 | direction window 1 s to 3 s, vote with peak-loud frames | snaps read "center" because room frames outvoted them |
| Sat 23:40 | pair each frame's loudness with the previous frame's tag | 16 snaps showed the tag leads its audio by one frame; 4/10 became 8/10 |
| Sun 07:55 | remove the second glasses app | an on-phone YAMNet scaffold at milestone 0; one app ships |
| Sun 09:00 | keep the single filtered classifier path | the two-path fix for knocks was measured but changing the phone app before noon was not worth the risk |
| Sun 09:15 | demo is siren, dog bark, clap | the sounds that detect every time through the glasses, and a clap is one the judge can make |
| Sun 09:30 | Android companion lands: call-style alerts, spoken replies, type-here page | built overnight by Iurii; the "answer for me" half arrives through the phone rather than a glasses phrase picker |
| Sun 09:40 | renamed Earshot to Cue | shorter, and it is what the glasses do: give you the cue |

## 9. Known limitations

- Front and behind are indistinguishable; the HUD shows "center" for both.
- Knocks are not detected, and only 2 of 6 doorbells are. The 600 Hz
  high-pass that alarms need through the G2 removes them. The measured fix,
  running YAMNet on the raw window as well and keeping the higher score per
  label (`tools/eval.py --dual`, 19 of 22 instead of 13), was a deliberate
  non-change on Sunday morning: the demo uses the sounds that work.
- The audio path has four hops (glasses, phone, laptop, phone, laptop,
  phone, glasses). The hub logs the round trip per window; end-to-end
  latency was not measured on video.
- 21 of the 22 eval clips are studio recordings. Only the smoke alarm went
  through the G2's microphones.
- The hub's address is baked into `plugin/app.json`; a new network means a
  new whitelist entry and a repack.

## 10. Prior art

Sound awareness for deaf users has won at three 2026 hackathons on phones or
headsets: SoundSense (Reality Hack at MIT, Best Use of Edge AI for Hardware),
Synesthesia (HackGT 13, The Shipyard 1st), Here (Knight Hacks IX). None ran
on display-only glasses. Even Hub's community catalog had captions apps and
nothing for non-speech sound. Details and links in `docs/RESEARCH.md`.
