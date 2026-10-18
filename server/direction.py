"""Turn the G2's per-frame `direction` tag into left / right / front / behind.

What the tag seems to be (from plugin/recordings/alarm_1.wav, not documented
by Even): an angle in degrees, -90 to +90, quantized to asin(k * 0.15):
0, 8, 17, 27, 37, 49, 66, 90. That is the shape of a two-microphone
time-difference estimate, which gives one axis only: it can separate the two
sides of the mic pair, but a sound and its mirror image across that axis read
the same. So if the pair is left/right, front and behind both read near 0.

Calibrate with the direction test (PLAN.md 4.3 step 6): the server's TIER0 log
line and GET / show the live estimate. Set SIGN so that a sound on the
wearer's left gives "left". Front and behind cannot be told apart, so a
centered angle is "center", which the plugin draws as a double vertical arrow
meaning "ahead or behind you".
"""

import time
from collections import deque
from statistics import median

# -1: positive angles are the wearer's LEFT. Set from the first live test
# (2026-10-17): with +1, a clap on the left showed the right arrow and vice versa.
SIGN = -1
# |angle| at or above this is a side; below it is CENTER.
SIDE_DEG = 25
# What a centered angle shows: "center" (ahead or behind), or "near" for no arrow.
CENTER = "center"
# How far back to look. The direction is read when the classifier result
# arrives, which for a cue is 2-of-3 windows at 0.5 s hop plus the round trip:
# 1 to 2 s after the sound. A 1 s window had already dropped a snap by then.
WINDOW_S = 3.0
# Which frames count: those at least PEAK_FRACTION as loud as the loudest frame
# in the window. A snap or knock is 1 to 3 frames far louder than the room, so
# only those frames vote; taking the loudest half let 20 room frames at -8/-17
# outvote them and every transient read "center". An alarm or siren is loud for
# many frames in a row, so the median still has plenty to average over.
PEAK_FRACTION = 0.5


def side_from_angle(deg: float | None) -> str:
    if deg is None:
        return "near"
    deg *= SIGN
    if deg >= SIDE_DEG:
        return "right"
    if deg <= -SIDE_DEG:
        return "left"
    return CENTER


class DirectionTracker:
    """Feed it every audio frame; ask it for the angle of the recent loud sound."""

    def __init__(self):
        self.frames: deque[tuple[float, int, float]] = deque()  # (time, tag, rms)

    def add(self, tag: int | None, rms: float, now: float | None = None) -> None:
        now = time.time() if now is None else now
        if tag is not None:
            self.frames.append((now, tag, rms))
        while self.frames and now - self.frames[0][0] > WINDOW_S:
            self.frames.popleft()

    def angle(self, now: float | None = None) -> float | None:
        now = time.time() if now is None else now
        recent = [(rms, tag) for t, tag, rms in self.frames if now - t <= WINDOW_S]
        if not recent:
            return None
        peak = max(rms for rms, _ in recent)
        loud = [tag for rms, tag in recent if rms >= peak * PEAK_FRACTION]
        return float(median(loud))

    def side(self, now: float | None = None) -> str:
        return side_from_angle(self.angle(now))
