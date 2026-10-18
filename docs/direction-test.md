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

## Snap test at 1 m, Sun 2026-10-18, ~1 am (Wendy, `server --dump`)

Wendy snapped 5 left, 5 right, 3 front, 3 behind at 1 m, with the server
writing every frame via `--dump` and `tools/dirtest.py` reading it back.
Tag one frame before the loudest frame, and on the loudest frame:

| set      | tag one frame before the peak | tag on the peak frame   |
|----------|-------------------------------|-------------------------|
| left x5  | +49 +37 +8 +49 +37            | -66 +27 +27 -66 -66     |
| right x5 | 0 -90 -90 +49 -66             | -90 -37 +90 -66 -17     |
| front x3 | -8 -8 -8                      | -8 0 -66                |
| behind x3| -17 -90 -17                   | -66 -66 -49             |

Findings:

- The tag arrives one frame ahead of the audio it describes. The tag on the
  loud frame itself is junk (large negative from every side), the tag on
  the frame before it is the real estimate. Likely the G2's speech
  enhancement delays the PCM but not the metadata. `TAG_LEAD_FRAMES = 1` in
  `server/direction.py` pairs each frame's loudness with the previous
  frame's tag.
- `SIGN = -1` was right: positive is the wearer's left.
- Replaying the 16 snaps through the fixed tracker: left 4/5, right 4/5
  (misses: one left read center, one right read left). Before the fix it
  was 4/10. Front reads center 2/3. Behind reads "right" 2/3, so behind is
  wrong more often than not; the HUD cannot fix that.
- Quiet room is -8 / -17, so "center" is also what you get when the tag
  simply did not update.

Pitch number: correct side 8 of 10 at 1 m.

## Status

Left and right ship with the pitch number above. Front and behind do not;
the plugin draws both as "center". If Even exposes per-microphone capture
(their FAQ lists it as on the roadmap), the same tracker could do a real
four-way estimate.
