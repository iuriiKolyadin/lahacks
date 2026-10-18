# Earshot PRD

Hackathon PRD. One page of what and why. How, who, and when are in `PLAN.md`.
Background research is in `docs/RESEARCH.md`.

LA Hacks AI Hackathon 2026, track Beyond the Digital. Team: Dara, Iurii, Nikhil,
Wendy. Deadline Sunday 2026-10-18, 12:00 pm.

## 1. Problem

Deaf and hard-of-hearing people miss sounds that aren't speech: a doorbell, a
knock, a siren, a smoke alarm, their own name called from across a room. Phone
apps exist for some of this, but by the time you take out a phone and look, the
sound is over and the information is useless. Even's G2 glasses already caption
speech with the built-in Conversate mode. Nothing on the glasses, or on Even's
app store, handles the sounds that aren't speech.

## 2. Users

A deaf or hard-of-hearing adult who already wears Even G2 glasses through the
day, at home, at work, walking. They need to know a sound happened, what it
was, and roughly where, without stopping what they're doing.

## 3. Why glasses

The cue has to arrive the instant the sound does, in their line of sight, with
their hands free. The G2 has no speaker, which costs a deaf user nothing. Even's
own brief for this hackathon asks for "a small, timely cue in the wearer's line
of sight."

## 4. Goals

1. The wearer learns about a doorbell, knock, siren, alarm, car horn, dog bark,
   or their own name within one second of it happening.
2. The display is blank the rest of the time.
3. A judge can put the glasses on and experience it in 60 seconds with nothing
   to configure.
4. Win the Even Realities challenge and place in Beyond the Digital.

## 5. Non-goals

- Captions or transcription of any kind. Conversate does it; we never show words.
- Translation, note-taking, summaries.
- Anything medical or emergency-routing. Even Hub bans these and it would
  disqualify us from the Even prize. We display sounds; we never call anyone.
- Fine-grained direction. Left, right, front, behind is enough.
- Any camera.

## 6. The demo (this is the acceptance test for the whole product)

Judge wears the G2. HUD is blank. A teammate:

| # | Does | Judge sees | Must pass by |
|---|---|---|---|
| 1 | Says "hey, [demo name]" from the left | `YOUR NAME` flash, `<-` if we have direction | 11 pm Sat |
| 2 | Plays a doorbell clip on the right | `doorbell  ->` for 4 s, then blank | 11 pm Sat |
| 3 | Knocks on the table behind | `knock` for 4 s, then blank | 11 pm Sat |
| 4 | Plays a smoke-alarm clip | Full screen `ALARM` until it stops | 11 pm Sat |
| 5 | Talks normally | `speech  <-` while talking, fades after 3 s | 11 pm Sat |
| 6 | Waits | Judge long-presses the temple; the pendant says "Hi, I'm deaf. Please face me and speak slowly." | 11 pm Sat |
| 7 | Hands the glasses to the next judge | Nothing to set up | 10 am Sun |

Pitch, once: "A deaf person misses the doorbell, the siren, and their own name.
Conversate already captions what people say to you. Earshot covers everything
Conversate ignores, shows nothing the rest of the time, and when you need to
answer, it speaks for you."

## 7. Requirements

P0 ships or we have no product. P1 ships if P0 is done by 11 pm Saturday. P2 is
a stretch.

| ID | Pri | Requirement | Pass if |
|---|---|---|---|
| R1 | P0 | Sound cue. Classify G2 mic audio; show one line for doorbell, knock, siren, alarm, horn, dog. | Each of the six test clips, played from a phone 1 m away, shows the right label within 1 s, 4 of 5 tries. |
| R2 | P0 | Alarm tier. Siren or alarm takes the whole display, full brightness, suppresses all other cues until 2 s after it stops. | Siren clip plus a doorbell clip at the same time shows only ALARM. |
| R3 | P0 | Blank by default. | 30 s of hallway noise with nobody addressing the wearer shows nothing. |
| R4 | P0 | Runs as an Even Hub Beta build on a physical G2. | Installed from the Beta group on the phone the G2 is paired to; survives a 5-minute phone lock; double-tap exits via the system dialog. |
| R5 | P1 | Name flash. The demo name, spoken from 2 m, shows YOUR NAME. | 4 of 5 tries; zero false flashes in 60 s of other speech. |
| R6 | P1 | Speech cue. Someone other than the wearer talking shows `speech`; the wearer's own voice does not. | Wearer talks: nothing. Teammate talks: cue within 1 s. |
| R7 | P1 | Direction. Every cue carries left, right, front, or behind. | Correct side 9 of 10 at 1 m. Source may be the G2's own direction tag or an external two-mic node; see PLAN.md. |
| R8 | P2 | Companion phone page with an event log a judge can scroll. | Exists and matches what the glasses showed. |
| R9 | P1 | Outbound phrase. Swipe on the temple picks one of three phrases, shown on the HUD. Long-press plays it from a speaker (an Android phone worn as a pendant). Phrases: "Hi, I'm deaf. Please face me and speak slowly." / "Could you repeat that?" / "Could you type it on your phone?" | A judge 1 m away hears the phrase within 1 s of the press, 5 of 5 tries. |

## 8. Success metrics

- Sound-to-HUD latency for a doorbell under 1.0 s, measured by filming the
  glasses and the speaker together and counting frames.
- Direction correct 9 of 10 at 1 m, if R7 ships.
- Zero false cues in 60 s of hall noise at the judging table.
- Five consecutive clean runs of the demo script Sunday morning.

## 9. Constraints from the sponsor (hard rules)

- App name 20 characters or fewer, must not contain "Even". Working name: Earshot.
- No medical, financial, or emergency-routing apps. Health apps are wellness
  only, no advice.
- Submitted as an `.ehpk` on a Beta group, running on a physical G2 at judging.
- Judged on: Made for G2, Originality, User Experience, Technical Execution.
  Judges ask: who uses this and when, why G2, can I try it right now.
- Even says teleprompters, translators, and note-takers won't stand out.

## 10. Risks

| Risk | Likelihood | If it happens |
|---|---|---|
| The G2 audio stream is speech-filtered and drops doorbells or knocks | medium | Use the phone mic (one-line change). If still bad, laptop mic classifies, glasses display only. |
| The G2 `direction` tag is null on current firmware | medium | External two-mic node if mic modules exist; otherwise ship without R7. |
| Venue noise causes false cues | high | Higher thresholds, require two consecutive windows, demo with a speaker and clean clips. |
| Phone can't reach the laptop | medium | Everything on one hotspot; whitelist the exact origin. |
| Packaging or Beta flow rejects us at the last minute | low | Pack a throwaway build at integration tonight, not Sunday morning. |

## 11. Open questions (answer tonight)

1. Demo name. A teammate's first name, two syllables.
2. Does the G2 `direction` field carry real data on current firmware? Decided
   by the Tier 0 test, PLAN.md section 4.3.
3. Does the MLH hardware table exist, and does it have microphone modules?

## 12. Decisions made

- 2026-10-17 15:00: robot arm dropped. No parts, no time.
- 2026-10-17 16:30: CPR and EMT dropped. Even Hub bans medical and emergency apps.
- 2026-10-17 17:00: captions dropped. Conversate exists; SDK has no STT; Even
  says caption apps won't stand out.
- 2026-10-17 17:10: phase 1 uses only the G2 mic. External hardware is for
  direction only, and only if the glasses can't provide it.
- 2026-10-17 19:20: ESP32 mic node dropped (the G2 mic is the only
  microphone we use; direction comes from the G2 tag or not at all). Added
  the outbound phrase, R9: an Android phone on a lanyard as the speaker,
  built by Iurii. The G2 has no speaker; audio always comes from a phone.
