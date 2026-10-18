# Deck decisions, final (Sun 2026-10-18, ~10:20)

Figma file `LA4VlcQtfR29T5VfQKtR3s`, page "Deck". Four slides, 1920x1080.
Everything below is what is on the slides now; earlier drafts are on the
"Archive" page in the same file.

## Name

**Cue.** Earshot rejected (Dara: "terrible name"). Other candidates (Perk,
Pinna, Heads Up, Fennec, Lookout...) rejected. Even rules: 20 chars max, no
"Even" in the name. `package_id` stays `com.earshot.lahacks` because the
installed Beta build keys on it.

## Look

- Dark. Every slide is a full-bleed photo or a dark gradient
  (#2b323c to #121417). The light "Sun on haze" board on the Brand page was
  the first lock; the deck moved dark once the Gemini photos came in.
- Text: cream #f3ead8, secondary grey #aab4b8, one sun-yellow #f2b64c rule
  per slide. Green #5ee07a only where a lens is.
- Type: Newsreader Medium for headlines (Light too thin, Bold rejected),
  Public Sans body, IBM Plex Mono for labels and lens text. Nothing under
  18 px.
- Labels, not sentences. No subtitles. No AI-sounding copy.
- Photos: Gemini edits of Even press shots. Prompts asked for the real lens
  strings (`<-----  siren`, `dog barking ----->`, `knocking ----->`).

## Slides

| # | headline | content |
|---|---|---|
| 01 | Your G2 sees speech. With Cue, it sees everything else. | eye close-up photo, small Cue wordmark, nothing else |
| 02 | They miss a sound every day. No glasses app shows one. | 1.5B / 1 in 2 / 0 / 3 in 4 with sources (WHO 2021; Bragg ASSETS 2016; Even Hub catalog; Findlater CHI 2019) over the shelf photo |
| 03 | How it works | labeled drawing: glasses -> Even app -> laptop hub -> iPhone, hand-drawn wires, one or two mono lines per device |
| 04 | When you need to answer, the phone does the talking. | drawn Android companion with the real lock-screen page and three replies, wired to the glasses in the photo |

Rejected headline shapes: anything with Cue as a rival device ("Cue shows
you..."); the G2 is the subject, Cue is installed on it. "Other smart
glasses see speech" rejected as false (the G2 sees speech via Conversate).

## Architecture slide, what is on it and why

Only the technically impressive facts, per `docs/ARCHITECTURE.md`:
direction angle on every frame (glasses); forwards audio, draws one line
(Even app); tag leads audio by 1 frame, 8 of 10 sides, alarm > cue > speech
(hub); YAMNet on device, 600 Hz high-pass or alarms vanish (iPhone).
Dropped on purpose: sockets, message formats, thresholds, the Android
companion (slide 04's job), and the dual-pass classifier (measured 13 ->
19 of 22, not shipped; say "next" out loud if asked).

## Honesty notes for the talk

- 19/22 is `tools/eval.py --dual`; the shipped app is single-pass 600 Hz.
- 1.0 s is classifier time on saved clips, not end-to-end on the glasses.
- Direction is left/right only; front and behind read the same.
- Bragg 2016 numbers came from a summary page, not the PDF.
- No name spotter exists; the demo uses snap instead.

## Repo branding

`cue-branding` merged into local main (460d44d) at ~10:30: Earshot -> Cue
in every user-facing string, `docs/deck/brand.md`. The branch's light
plugin UI was dropped in the merge; main's dark UI with the off tier stays
(it matches the dark deck and the Android app's tier colors). Not pushed. `main` also had committed merge
markers in `server/main.py` and `server/fake_glasses.py` at 08:56.
