# Direction: what the G2's `direction` tag gives us

Status Sat 2026-10-17, 11:15 pm. Written by Dara from Wendy's recording and
Nikhil's calibration notes in `server/direction.py`.

## Verdict

Tier 0 works. The glasses report a direction on every audio frame, with no
extra hardware. It is left/right only.

## Evidence

`plugin/recordings/alarm_1.jsonl`, 322 frames from the real G2 during a smoke
alarm, zero null values. Distinct tag values seen:

```
-90  -66  -49  -37  -27  -17  -8  0  27
```

Counts: -8 (118 frames), -17 (112), -37 (30), -27 (24), 0 (19), -49 (9),
-66 (7), -90 (2), +27 (1). Median -17, also -17 over the loudest half of the
frames.

Those values are `asin(k * 0.15)` in degrees for k = 0..6, plus 90. That is
the shape of a two-microphone time-difference estimate: one axis only. It can
tell the two sides of the mic pair apart, but a sound and its mirror image
across that axis read the same angle. So front and behind both read near 0.

Nikhil's first live test: with the raw sign, a clap on the wearer's left
showed the right arrow, so `SIGN = -1` in `server/direction.py`. Angles at or
beyond 25 degrees are a side; smaller is "center", which the plugin draws as
arrows both up and down, meaning "ahead or behind you".

## What the HUD can honestly show

- left, right: yes.
- front vs behind: no. The glasses cannot tell them apart. The plugin shows
  "center" for both.
- near (no arrow) when the tag is missing: only on the phone mic or old
  firmware; the recording had none.

## Fix, Sun 2026-10-18 early am: transients read "center"

A snap by the right ear showed the double vertical arrow. Cause: the server
reads the direction when the classifier result lands, which for a cue is
2-of-3 windows at 0.5 s hop plus the round trip, so 1 to 2 s after the snap.
The tracker only kept 1 s of frames and voted with the loudest half of them,
so by then the snap's 1 to 3 frames were gone or outvoted by 20 room frames
at -8/-17, which is "center". `server/direction.py` now keeps 3 s and votes
only with frames at least half as loud as the loudest one in the window. An
alarm is loud for many frames so its median is unchanged (test added in
`server/test_state.py`).

## Still to do

The four-position test from the plan: stand 1 m away, talk 5 s from left,
right, front, behind, read the angle off the server's `TIER0` log line, and
write the numbers here. Then the pitch number: correct side N of 10 at 1 m.
