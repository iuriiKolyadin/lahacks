# Cue deck: four slides

Copy and layout only. Built in Figma from the Brand page reference slide
(file `LA4VlcQtfR29T5VfQKtR3s`). Every number below is from `PRD.md`,
`docs/eval-2026-10-17.md`, `docs/direction-test.md`, or the code; anything I
could not verify is marked **[unverified]**.

Brand rules that apply to every slide: Sun on haze background (gradient plus
one warm bloom top right), black ink, Public Sans body, Newsreader headline,
one accent rule per slide, green and monospace only inside a lens card,
headline top-left or bottom-left, captions bottom-right, no boxes, no icons.

Lens strings are what `plugin/src/hud.ts` actually draws: lowercase labels,
side arrows `<-----` and `----->` on the label's own line.

Pitch is 2 to 3 minutes: about 30 s, 50 s, 45 s, 35 s.

---

## 01 Title  (product thinking and impact)

**Kicker** `LA HACKS 2026  ·  EVEN G2`

**Headline (bottom-left, Newsreader, 200 px)** `Cue`

**Sentence (right column, Newsreader, 44 px)**
The glasses stay dark until a sound you can't hear matters.

**Sub (right column, Public Sans)**
Sound awareness for deaf and hard of hearing people, on Even G2.

**Team line (bottom-right, small)**
Dara Miao · Iurii Kolyadin · Nikhil Marisetty · Wendy Wang

**Lens card (top-right, one)** `<-----  doorbell`

**Photo** wearer (press portrait with the HUD), left, 840×500.

**Layout** Exactly the Brand page reference slide. Accent rule above `Cue`.
Nothing else.

**Speaker notes**
- A deaf person misses the doorbell, the siren, and their own name. Phone
  apps exist; by the time you take the phone out the sound is over.
- The G2 already captions speech (Conversate). Nothing on the glasses or in
  the Even store covers the sounds that are not speech. That gap is Cue.
- The cue lands in your line of sight, hands free, within about a second,
  and the display is blank the rest of the time.
- Transition: "Here is everything the wearer ever sees."

---

## 02 What the wearer sees  (execution and polish)

**Kicker** `WHAT THE WEARER SEES`

**Headline (top-left, 72 px)** One line, a few seconds, then nothing.

**Five lens cards in a row (equal width, the only dark objects)**

| card | lens string | caption under it (Public Sans, muted) |
|---|---|---|
| 1 | *(blank)* | Most of the time. The lens is dark. |
| 2 | `<-----  knock` | A cue. Four seconds, then dark. |
| 3 | `alarm` | Full brightness, holds until 3 s after it stops, beats everything. |
| 4 | `<-----  your name` | Someone called you. Four seconds. |
| 5 | `speech  ----->` (dim green) | Someone else is talking. Fades 3 s after they stop. |

**Demo steps (bottom band, numbered, hairline between rows)**
```
01  A snap by your left ear                      <-----  snap
02  A doorbell rings on your right               doorbell  ----->
03  A knock on the table                         knock
04  A smoke alarm goes off                       alarm
05  Someone talks to you                         speech
```
Then hand the glasses to the next person. Nothing to set up.

Snap and clap are real cues in `server/labels.py` (`Finger snapping`,
`Clapping`, threshold 0.5, 3 s cooldown) and in the plugin's `DEMO_STATES`.
They replace the name step, which has no code behind it (see flags).

**Photo** none, or "back of head" small bottom-right if the row feels bare.

**Layout** Headline top-left; the five cards across the middle third; the
six steps as a numbered list below with the lens string right-aligned in a
small lens card per row; closing line bottom-left. Accent rule above the
headline.

**Flags (from the code, not the PRD; the PRD is stale)**
- **Name flash does not exist.** No Porcupine, no `name.py`, nothing in the
  iOS app; `state.py` has a `name` state that nothing triggers. Card 4
  (`<-----  your name`) must go unless someone ships it by 11 am. Replace
  it with `<-----  snap` to keep five cards, or show four.
- **Pendant and long-press do not exist in the repo.** `plugin/src/main.ts`
  handles only double-tap exit and system exit; no `LONG_PRESS_EVENT`,
  no phrase picker, no `say` frame is sent. `server/main.py` relays `say`
  to `/ws/pendant`, but there is no `pendant/` folder. Do not put the
  pendant on a slide unless Iurii's app is in hand and the plugin sends.
- Whether `alarm` renders in caps on the real lens depends on `styled()` in
  `hud.ts`; use what the glasses actually show.

**Speaker notes**
- Five states, strict priority: alarm beats name beats cue beats speech.
  A cue keeps the direction it started with so the arrow never jitters.
- Alarm holds 3 s, not 2, because a real G2 smoke-alarm recording had gaps
  up to 2.5 s between detections and a 2 s hold blinked off mid-alarm.
- The demo is the acceptance test: a judge wears it for 60 s with nothing
  to configure.
- Transition: "Four devices make that one line appear. Here is how."

---

## 03 Architecture  (technical depth)

**Kicker** `HOW IT WORKS`

**Headline (top-left, 72 px)** The glasses listen. A phone decides. The lens draws.

**Four numbered columns, hairline on top of each, no boxes, no arrows**

```
01  G2 glasses                02  Glasses phone              03  Server laptop                 04  Classifier iPhone
    Two microphones.              Even app loads the Cue         One Python process.               YAMNet, the TFLite model
    16 kHz audio over             plugin in a WebView.           Receives audio frames,            from the iOS sample app.
    Bluetooth, each frame         Base64 PCM frames up a         keeps a 3 s direction             521 classes, mapped to
    tagged with a direction       WebSocket; HUD states          window, runs the state            doorbell, knock, siren,
    number nobody documents.      back down; one text            machine, sends one state          alarm, horn, dog, speech.
                                  container, 150 ms min          to the glasses, relays            Scores back every 0.5 s.
                                  between writes.                "say" to the pendant.
```

**Two findings, set as a short list under the columns (left half)**

*The direction tag leads its audio by one frame.* The G2 reports an angle
on every audio frame; the tag on the loud frame is junk, the tag on the
frame before it is the real estimate. Pairing each frame's loudness with
the previous frame's tag took the correct side from 4 of 10 to 8 of 10.

*No single filter serves alarms and knocks.* The G2 stream is tuned for
voices and buried under rumble below 300 Hz. A 600 Hz high-pass is the only
way a real smoke alarm registers, and it erases every knock. Running YAMNet
on the filtered window and the raw window, keeping the higher score per
label, takes the saved clips from 13 of 22 to 19 of 22 with no new false
cues. **Say "we found" if the iPhone app still runs once; say "we run" only
if the dual path ships (see flags).**

**Lens card (right half, large)** `<-----  knock`
**Caption under it** "Left and right are real. Front and behind read the
same, because two mics give one axis. We show an arrow for the sides and
nothing for the rest."

**Photo** render (the transparent-frame product shot with the green
projector), right half above the lens card. If space is tight, drop the
photo and keep the lens card.

**Layout** Headline top-left. Columns across the upper middle, each with
its number in accent-colored monospace and a 1 px hairline above. Findings
bottom-left in two short paragraphs with italic lead-ins. Photo and lens
card stacked on the right. Accent rule above the headline only. All
hierarchy by size and hairlines; nothing is drawn as a box or an arrow.

**Flags (from the code)**
- **The dual run is not deployed.** `AudioClassificationHelper.swift`
  high-passes everything (`GlassesAudioFilter.highPass`, then `normalize`)
  and classifies once; `server/main.py` forwards raw frames and does no
  filtering. The dual path exists only in `tools/eval.py --dual`. Column 04
  must describe the single high-passed run unless Nikhil adds the second
  `classify` call before the deck is final.
- The server does not run YAMNet; the iPhone does. The server's job is
  direction (`direction.py`), the state machine (`state.py`), label
  thresholds and hits (`labels.py`), and the relays. Column 03 above is
  correct as written.
- All four devices sit on one hotspot; the glasses phone hosts it
  (`README.md`). Say it, do not draw it.
- 322 frames, zero nulls, nine distinct tag values: `docs/direction-test.md`.
- Thresholds 0.5 for cues, 0.3 for alarm and siren, 2-of-3 windows
  (2-of-4 for alarm and siren): `server/labels.py`.

**Speaker notes**
- Nothing runs in the cloud. Glasses to phone to a laptop to a second
  phone, all on one hotspot. The laptop is a 300-line state machine.
- The undocumented `direction` int16: we logged every frame, lined it up
  with loudness, and saw it was one frame early. "The tag describes the
  audio you have not received yet."
- The dual-run classifier: no single cutoff serves alarms and knocks, so we
  run the model twice every half second. YAMNet is well under 100 ms per
  window on the iPhone, so it costs nothing we can feel.
- Transition: "We measured all of this last night."

---

## 04 Numbers  (originality and insight)

**Kicker** `MEASURED LAST NIGHT  ·  tools/eval.py --dual`

**Headline** none; the numbers are the headline.

**Three big stats (Newsreader, 200 px, light), captions under each**

| stat | caption |
|---|---|
| **19** /22 | clips detected after running the model on filtered and raw audio. 13 before. |
| **0** | false cues across six noise clips: vacuum cleaner, crying baby. |
| **1.0** s | median from clip start to lens for alarm, siren, knock, and horn. |

**Fourth stat, smaller, right-aligned** **8** of 10 · correct side at 1 m,
from 4 of 10 before the one-frame fix.

**Per-class row (hairline above each, label small, fraction large)**
```
alarm 4/4   siren 3/3   doorbell 4/6   knock 3/3   horn 2/3   dog 3/3
```

**Footnote (bottom-left, muted)**
21 of the 22 clips are studio recordings. The one real G2 recording, a smoke
alarm, shows `alarm` at 1.0 s and holds to the end. Doorbells ring twice;
the second ring is what crosses the threshold, median 3.2 s.

**Repo line (bottom-right, monospace)** `github.com/iuriiKolyadin/lahacks`

**Photo** desk (glasses on the table with the HUD) as a narrow band at the
very top, or none.

**Layout** Three stats across the upper half, left-aligned to the margin,
captions directly under each in Public Sans. Per-class row across the
middle with hairlines. Footnote bottom-left, repo bottom-right. Accent rule
under the kicker.

**Flags (from the code)**
- **19/22 is an eval result, not the shipped pipeline.** The deployed
  pipeline (600 Hz high-pass, single run, what the iPhone app does today)
  scored 13/22 on the same clips: alarm 4/4, siren 3/3, doorbell 2/6, knock
  0/3, horn 1/3, dog 3/3, still 0 false cues. Two honest versions of this
  slide: (a) if the dual path ships, show 19/22 as is; (b) if not, lead
  with **0** false cues and **4/4** alarms and **3/3** sirens on the shipped
  pipeline, and present 13 to 19 as "what we found and will ship." Decide
  before building the slide.
- The 1.0 s is classifier time on saved clips, not end-to-end through
  Bluetooth, phone, laptop, and iPhone. The PRD target of under 1.0 s
  end-to-end was **not measured**; do not claim it.
- "1.0 s median" is for four classes only; dog is 2.5 s, doorbell 3.2 s.
  The caption names the four.
- Direction 8 of 10 is left and right only (4/5 and 4/5); front reads
  center 2/3, behind reads wrong 2/3.

**Speaker notes**
- 13 of 22 to 19 of 22 with zero new false cues, from one change: run the
  model on both the filtered and the raw window.
- The zero matters more than the nineteen. The glasses are blank by default;
  a false cue is the product failing.
- Direction cost no hardware; it cost reading 322 frames of an undocumented
  field and noticing it was one frame early.
- Close: "Put the glasses on." Hand them over. That is the last slide.
