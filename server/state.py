"""The HUD state machine (PRD.md section 5).

Feed it classifier windows with observe(), and call step() on a timer. step()
returns a state frame for the plugin when what the HUD should show changes,
else None. Time is always passed in, so tests can drive it.

Priority: alarm > name > cue > speech > idle.
- alarm or siren holds until ALARM_HOLD_S after the last detection, and while
  it is up every other detection is ignored.
- name shows for NAME_TTL_S.
- a cue shows for CUE_TTL_S; a newer cue replaces an older one; a label is
  not re-cued within its COOLDOWN_S.
- speech (not the wearer's own) holds while detected and fades SPEECH_FADE_S
  after the last detection.

Direction (left/right/front/behind/near) is passed in with each window. A cue
or name keeps the direction it started with, so the arrow does not jitter
while it is up; an alarm shows the most common of its last 3 detections; speech
follows the latest.
"""

from collections import Counter, deque

import labels as L

# 3 s, not PRD's 2 s: on a real G2 alarm recording detections came up to 2.5 s
# apart, so a 2 s hold blinked ALARM off mid-alarm.
ALARM_HOLD_S = 3.0
NAME_TTL_S = 4.0
CUE_TTL_S = 4.0
SPEECH_FADE_S = 3.0

IDLE = {"state": "idle"}


class StateMachine:
    def __init__(self, threshold=None, hits=None, cooldown_s=None):
        self.threshold = threshold or L.THRESHOLD
        self.need = {label: (hits or L.HITS).get(label, (1, 1)) for label in self.threshold}
        self.cooldown_s = cooldown_s or L.COOLDOWN_S
        self.recent = {label: deque(maxlen=self.need[label][1]) for label in self.threshold}
        self.alarm_label = None
        self.alarm_last = float("-inf")
        self.alarm_dirs: deque[str] = deque(maxlen=3)
        self.name_until = float("-inf")
        self.name_dir = "near"
        self.cue_label = None
        self.cue_until = float("-inf")
        self.cue_dir = "near"
        self.cue_started: dict[str, float] = {}
        self.speech_last = float("-inf")
        self.speech_dir = "near"
        self.last_frame = IDLE

    def alarm_active(self, now: float) -> bool:
        return now - self.alarm_last <= ALARM_HOLD_S

    def observe(
        self, scores: dict[str, float], now: float, speaker_role: str = "unknown", direction: str = "near"
    ) -> None:
        """Take one classifier window: {our label: score}, and where the sound came from."""
        fired = []
        for label, thr in self.threshold.items():
            self.recent[label].append(scores.get(label, 0.0) >= thr)
            if sum(self.recent[label]) >= self.need[label][0]:
                fired.append(label)

        alarms = [l for l in fired if l in L.ALARM_LABELS]
        if alarms:
            if not self.alarm_active(now):
                self.cue_label = None  # an alarm wipes whatever cue was up
            # a label can fire on an earlier window's hits, so its score here may be missing
            self.alarm_label = max(alarms, key=lambda l: scores.get(l, 0.0))
            if not self.alarm_active(now):
                self.alarm_dirs.clear()
            self.alarm_last = now
            self.alarm_dirs.append(direction)
            return
        if self.alarm_active(now):
            return  # R2: everything else suppressed while the alarm holds

        cues = [l for l in fired if l in L.CUE_LABELS and self._off_cooldown(l, now)]
        if cues:
            label = max(cues, key=lambda l: scores.get(l, 0.0))
            self.cue_label = label
            self.cue_until = now + CUE_TTL_S
            self.cue_started[label] = now
            self.cue_dir = direction

        if "speech" in fired and speaker_role != "self":
            self.speech_last = now
            self.speech_dir = direction

    def name_detected(self, now: float, direction: str = "near") -> None:
        if not self.alarm_active(now):
            self.name_until = now + NAME_TTL_S
            self.name_dir = direction

    def _off_cooldown(self, label: str, now: float) -> bool:
        started = self.cue_started.get(label)
        return started is None or now - started >= self.cooldown_s.get(label, 0.0)

    def current(self, now: float) -> dict:
        """What the HUD should show right now."""
        if self.alarm_active(now):
            # most common of the last 3; ties go to the most recent
            counts = Counter(self.alarm_dirs)
            best = max(reversed(self.alarm_dirs), key=lambda d: counts[d])
            return {"state": "alarm", "label": self.alarm_label, "dir": best, "ttl_ms": 0, "level": 4}
        if now < self.name_until:
            return {"state": "name", "label": "name", "dir": self.name_dir, "ttl_ms": int(NAME_TTL_S * 1000), "level": 4}
        if self.cue_label is not None and now < self.cue_until:
            return {"state": "cue", "label": self.cue_label, "dir": self.cue_dir, "ttl_ms": int(CUE_TTL_S * 1000), "level": 4}
        if now - self.speech_last <= SPEECH_FADE_S:
            return {"state": "speech", "label": "speech", "dir": self.speech_dir, "ttl_ms": 0, "level": 2}
        return IDLE

    def step(self, now: float) -> dict | None:
        """The new frame if the HUD should change, else None."""
        frame = self.current(now)
        if frame == self.last_frame:
            return None
        self.last_frame = frame
        return frame
