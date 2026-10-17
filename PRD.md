# Earshot — sound awareness glasses for deaf and hard-of-hearing users

LA Hacks AI Hackathon 2026. Written Sat 2026-10-17, 4:45 pm. Deadline Sun 12:00 pm.
Working name "Earshot" (7 chars, no "Even"). Change it if someone has a better one.

## 1. One line

Glasses that stay blank until a sound you can't hear matters, then show what it was
and which way it came from.

## 2. Who, when, why glasses

- **Who:** a deaf or hard-of-hearing person at home, in an office, or on the street.
- **When:** a doorbell rings behind them, a siren comes from the left, someone says
  their name from across the room, a fire alarm goes off.
- **Why glasses and not a phone:** the sound is already over by the time you pull
  out a phone. The cue has to be in your line of sight, instantly, with a direction,
  while your hands and eyes are busy. The G2 has no speaker, which costs a deaf
  user nothing. The Even judges ask exactly these three questions.

## 3. The 60-second demo (this is the product)

Judge wears the G2. Four sound sensors sit on a small board on the table or clip
to a cap. HUD is blank.

1. Teammate on the judge's left says "hey, [judge's name]."
   HUD: `<-  "hey Alex"` and `YOUR NAME` flashes.
2. Phone on the right plays a doorbell.
   HUD: `doorbell  ->`
3. Teammate behind knocks on the table.
   HUD: `knock  (behind)`
4. Phone plays a smoke-alarm sound.
   HUD goes full screen: `ALARM` + direction. Nothing else shows until it stops.
5. Hand the glasses to the next judge. Nothing to configure.

Pitch line: "A deaf person misses the doorbell, the siren, and their own name.
Earshot puts those three things in their line of sight, with a direction, and
shows nothing the rest of the time."

## 4. Scope

**Must ship (the demo above):**
- Sound class detection for a fixed set: speech, doorbell, knock, siren, alarm,
  car horn, dog bark. Everything else is ignored.
- Direction as one of four quadrants (left, right, front, behind) from four
  external sound sensors.
- Captions from the G2 mic when the class is speech, last 2 lines, with the side
  marker.
- Name detection: the wearer's name in a caption triggers a `YOUR NAME` flash.
- Urgency tiers: alarm/siren take the whole display and suppress everything;
  doorbell/knock/horn/name show for 4 s; speech captions show while speech
  continues and fade 3 s after it stops; everything else shows nothing.
- Blank display by default. The judges will watch for this.
- Beta build installed on a physical G2, survives 5-minute phone lock, double-tap
  exits.

**Should ship if the must list is done by 11 pm:**
- Direction arrow as a block-character bar instead of text.
- Gemini writes a one-line summary of the last minute on long-press ("doorbell
  twice, someone said your name").
- Companion phone page shows the event log for the judge to scroll.

**Won't ship:**
- Translation, note-taking, a general captions app. Even says these won't stand out
  and eight already exist.
- Any medical or emergency-routing feature. Even Hub bans them. We display sounds;
  we never call anyone.
- Camera, P4-EYE, robot arm. Not needed for this product.
- Fine-grained direction. Four quadrants is what won at Reality Hack 2026.

## 5. System

```
 G2 mics ──BLE──▶ phone plugin ──ws──▶ laptop server (FastAPI)
   (PCM + direction tag)              - YAMNet class (+ Whisper captions)
                                      - direction: Tier 0 tag, or Tier B
 laptop mic + webcam mic ──USB──▶       two-mic time delay
                                      - urgency state machine
                                      - one JSON state, pushed back over ws
                                               │
                                phone plugin renders state ──BLE──▶ G2 HUD

 optional edge node: Arduino UNO Q + webcam mic runs the classifier
 (audio_classification brick) and publishes events over its web_ui WebSocket
```

- **Direction, three tiers. We have no sound-sensor modules, so the server
  takes direction from whichever tier works. Test Tier 0 first, on real
  glasses, before 6 pm:**
  - **Tier 0, the G2's own direction tag.** SDK 0.0.16 `AudioEvent` has
    `direction: number | null`, documented as "raw glasses direction tag for
    this PCM frame", a signed int16 whose unit and range the SDK does not
    convert. Null on the phone mic or old hosts. If current firmware fills it
    in, direction is free and on-glasses, which is the best possible story.
    Test: log `audio.direction` while a teammate talks from left, right, front,
    behind. If the numbers move with position, map them to quadrants and ship.
    If always null, fall to Tier B.
  - **Tier B, two mics on the laptop.** The laptop's built-in mic plus a USB
    webcam mic (nearly every webcam has one), placed about 1 m apart on the
    table, or one on each side of a cap. The server reads both as audio devices
    and computes left/right from level difference plus time delay (GCC-PHAT).
    Loses "behind"; the demo becomes left/right/near. Zero new hardware.
    Verify tonight: plug a webcam in, open Audio MIDI Setup, confirm it appears
    as an input.
  - **Tier C, no direction.** Product is sound class plus urgency only. Still a
    valid demo (doorbell, alarm, your name); loses the arrow. Only if 0 and B
    both fail.
- **Classification:** YAMNet (521 AudioSet classes, TFLite) on the laptop,
  mapped to our seven classes, 0.975 s window. **Input source is a decision, not
  a given:** the G2 stream is "processed PCM" per the SDK, and Even markets
  "AI voice isolation" on the 4-mic array, so doorbells and sirens may be
  attenuated. Community apps (MuSe music ID, Birdie bird calls, Applied
  Resonance machine sounds) do classify non-speech from the G2 mic, so it
  probably works, but knocks are the risk. Fallbacks in order:
  `AudioInputSource.Phone` (one-line change), then the laptop or webcam mic
  feeding YAMNet directly with the glasses as display only. Edge-AI option for
  the hardware story: run the classifier on the Arduino UNO Q's
  `audio_classification` brick with a USB webcam mic and publish events over
  its `web_ui` WebSocket; the laptop then only fuses and renders.
- **Captions:** faster-whisper on the laptop on the same PCM, 2-second chunks,
  only while YAMNet says speech. Deepgram as fallback if latency is bad.
- **Fusion rule:** a sound class gets the direction reported in the same
  300 ms window by whichever tier is active. If none, direction is "near" with
  no arrow.
- **Transport:** one WebSocket from the plugin to the laptop. Plugin sends PCM up,
  server sends state down. Whitelist entry is the laptop's LAN origin. Phone and
  laptop on the same hotspot, not venue Wi-Fi.
- **Optional QNX node:** if someone wants the QNX prize, the QNX Pi takes the
  serial reader plus a TFLite classifier on the sensor stream at fixed priority and
  publishes direction over WebSocket. Satisfies both QNX hard requirements (QNX OS
  plus an oss.qnx.com AI module). Decide by 7 pm; otherwise skip.

## 6. HUD states

| State | Display | Hold |
|---|---|---|
| idle | blank | until event |
| speech | 2 caption lines, side marker `<-` / `->` / `(behind)` | fade 3 s after speech ends |
| name | caption + `YOUR NAME` on line 1 at full brightness | 4 s |
| cue | `doorbell  ->` one line, centered | 4 s |
| alarm | full screen `ALARM` / `SIREN` + direction, brightness 4 | while detected + 2 s |

Text only. No images. One `textContainerUpgrade` per state change, debounced
at 150 ms. Calibrate on the real glasses at 5 pm; the simulator font differs.

## 7. Hardware we have and use

Actual inventory, confirmed Sat 5:30 pm: Even G2 + iPhone, 2 brushless DC
motors, camera(s), QNX Pi, breadboard, ESP32-P4-EYE, Arduino UNO Q. Nothing
else. No sound sensors, no jumper wires, no MLH kit.

| Item | Role |
|---|---|
| Even G2 + iPhone | HUD, mic, touch, and (if Tier 0 works) direction |
| laptop | server, YAMNet, Whisper, Tier B mic |
| USB camera(s) | webcam mic as the second mic for Tier B |
| Arduino UNO Q | optional edge classifier node, needs a USB mic or webcam |
| QNX Pi | optional, see §5 |
| second phone | hotspot |

Not used: P4-EYE, breadboard, brushless motors, arm parts.

## 7a. Things we have to get (check off tonight)

**Only if the MLH hardware table exists and has them (nice to have, not required)**
- [ ] A USB microphone, any kind. Better than a webcam mic for Tier B.
- [ ] 4x sound sensor modules with analog out, plus jumper wires, if they exist.
      Would upgrade Tier B to four quadrants. Don't block on this.

**Already in the bag, confirm they're actually here**
- [ ] Even G2, charged, paired, firmware updated, developer access on.
- [ ] iPhone with the Even app 2.2.10 or newer, auto-lock set to Never.
- [ ] The USB camera(s) plus whatever adapter the laptop needs (USB-C to USB-A).
      Confirm at least one shows up as an audio input.
- [ ] A USB hub if the laptop runs short of ports.
- [ ] Laptop chargers. Everyone's.
- [ ] A second phone for the hotspot, so the demo phone isn't also the router.

**Physical demo props, buy or improvise**
- [ ] Tape and a marker, for L / R labels on the table so judges see the setup.
- [ ] A cap if the webcam mic rides on the head for Tier B.
- [ ] A Bluetooth speaker or a second phone to play the test sounds at volume.
      A phone speaker is too quiet in the hall.

**Sound clips on a phone, downloaded tonight, not streamed at the table**
- [ ] doorbell (two-tone), 3 s
- [ ] knock on door, 2 s
- [ ] smoke alarm beep, 5 s
- [ ] police siren, 5 s
- [ ] car horn, 2 s
- [ ] dog bark, 2 s
- [ ] 30 s of hallway crowd noise, for threshold tuning

**Software and accounts, set up before 7 pm**
- [ ] Even developer account with developer access enabled (whoever owns the Beta
      group).
- [ ] Node 20+, `npm install` inside the plugin folder (pulls the Even CLI and
      simulator).
- [ ] Python 3.11 or 3.12 for the server. TensorFlow and faster-whisper don't yet
      ship wheels for 3.13 on every platform; check at install time.
- [ ] YAMNet TFLite model file downloaded locally (the TF Hub archive), so the
      server doesn't fetch it at the table.
- [ ] faster-whisper `base.en` model pulled once so the first run isn't a download.
- [ ] Deepgram API key as the captions fallback. Free tier is enough.
- [ ] Gemini API key only if the long-press summary ships.
- [ ] ffmpeg on the laptop (already installed on Dara's Mac).
- [ ] Devpost project created, team members added, Even Realities and Beyond the
      Digital challenges selected.

## 8. Prizes this hits, and how

- **Even Realities** (1st = G2 per member): assistive, not medical. Blank by
  default, one timely cue. Not a teleprompter, translator, or note-taker.
- **Beyond the Digital**: embedded sensors plus edge audio AI plus AR display.
- **Applied Intelligence**: a real accessibility problem for a named user.
- **QNX**: only with the optional node.
- **Gemini**: only with the long-press summary.
- **ElevenLabs**: skip. The G2 has no speaker and bolting on a voice reply
  dilutes the product.

## 9. Team split (3 or 4 people)

| Person | Owns | Done when |
|---|---|---|
| Glasses | plugin: WebSocket, PCM up, state render, lifecycle, Beta packaging | state JSON from a mock server renders every §6 state on the real G2 |
| Audio | server: YAMNet + Whisper on PCM, class mapping, name match | a recorded doorbell and a spoken name produce correct events in the log |
| Direction | Tier 0 test on real glasses, then Tier B two-mic reader, then fusion | talking from left and right shows the right side in the server log |
| 4th (if any) | Devpost page, video, README, QNX node | submission draft exists by 10 pm |

Every node has a mock so nobody waits: server `--mock` emits fake events; plugin
has a "demo" button cycling §6 states; direction reader has `--mock`.

## 10. Timeline

| When | Checkpoint |
|---|---|
| 5:30 pm | asr template on the real G2, log `audio.direction` from 4 positions, dump PCM to a WAV while playing doorbell/siren/knock. Decides Tier 0 and the classifier input. Visit Even table with any questions. |
| 6:00 pm | Server emits mock state; plugin renders it on the G2 over the hotspot. |
| 7:00 pm | Direction tier chosen and working on the bench. YAMNet classifies a doorbell clip from the chosen input. Decide QNX. |
| 8:00 pm | Even table closes. Any SDK question must be asked before this. |
| 9:00 pm | PCM from the glasses reaches the server; YAMNet runs on live audio. |
| 11:00 pm | **Hard checkpoint: full demo loop works end to end once.** If not, cut captions and ship cue + direction only. |
| 1:00 am | Urgency tiers, name flash, phone-lock recovery tested. |
| 8:00 am | Pack .ehpk, Beta group, install, test. Record backup video. |
| 10:00 am | Five full rehearsals with someone who hasn't worn the glasses. |
| 11:00 am | Devpost and Beta submitted. Don't touch code after this. |

## 11. Risks and the fallback for each

| Risk | How we find out | Fallback |
|---|---|---|
| Venue noise makes YAMNet flaky | 7 pm bench test in the hall | demo with phone-played clean clips at the table; raise thresholds |
| G2 `direction` tag is always null on current firmware | 5:30 pm test | Tier B two-mic time delay on the laptop |
| G2 stream strips non-speech sounds (voice isolation) | 5:30 pm WAV test | `AudioInputSource.Phone`, then laptop/webcam mic into YAMNet |
| No webcam has a mic | 5:30 pm | laptop mic only; Tier C, no direction |
| Mic stream dies on phone lock | 1 am test | re-enable `audioControl` and reconnect ws on foreground; persist state in localStorage |
| Phone can't reach laptop | 6 pm | hotspot off a second phone; if still blocked, cloudflared tunnel with https whitelist |
| Whisper latency over 2 s | 9 pm | Deepgram streaming, or cut captions entirely (cue + direction is still the product) |
| Evenhub pack rejects manifest | 8 am | pack once at 6 pm with the mock build to shake out the manifest early |
| Name detection false positives | 1 am | require exact token match plus the speech class |

## 12. Success numbers (pick one for the pitch)

- Sound-to-HUD latency under 1.0 s for a doorbell. Measure with a phone video of
  the glasses and the speaker; count frames.
- Direction correct 9 of 10 times at 2 m on the bench.

## 13. Open questions (answer by 6 pm)

1. App name. "Earshot" unless someone objects.
2. Whose name is the demo name? Use the judge's name typed into the phone page at
   the table, or a fixed teammate name.
3. QNX node: yes or no. Costs one person 4 hours. Without a Pi Camera it can only
   be the classifier-on-sensor-stream role, and we have no sensors, so likely no.
4. Who has the Even developer account the Beta group goes under?

## 14. Prior art we're building on, for the Devpost page

- SoundSense, Reality Hack 2026, Best Edge AI Hardware: sound sensor array on an
  Arduino UNO Q, whisper.cpp, captions plus direction, shown on a headset.
- Synesthesia, HackGT 13, Shipyard 1st: Pi Pico mic array, YAMNet, siren and knock
  shown with direction on a phone.
- Here, Knight Hacks IX: mic array plus camera plus haptic belt, urgency tiers.
- None ran on display-only glasses. Nothing on Even Hub does this.
