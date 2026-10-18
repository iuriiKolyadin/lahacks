"""The HUD state machine (PLAN.md section 4.2 step 5).

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
"""

import labels as L

ALARM_HOLD_S = 2.0
NAME_TTL_S = 4.0
CUE_TTL_S = 4.0
SPEECH_FADE_S = 3.0

IDLE = {"state": "idle"}


def direction_from_tag(tag: int | None) -> str:
    """Map the G2's raw `direction` int16 to a side.

    Tier 0 is undecided until the direction test in docs/direction-test.md.
    Until it has thresholds, every cue is `near` (no arrow).
    """
    return "near"


class StateMachine:
    def __init__(self, threshold=None, min_hits=None, cooldown_s=None):
        self.threshold = threshold or L.THRESHOLD
        self.min_hits = min_hits or L.MIN_HITS
        self.cooldown_s = cooldown_s or L.COOLDOWN_S
        self.hits = {label: 0 for label in self.threshold}
        self.alarm_label = None
        self.alarm_last = float("-inf")
        self.name_until = float("-inf")
        self.cue_label = None
        self.cue_until = float("-inf")
        self.cue_started: dict[str, float] = {}
        self.speech_last = float("-inf")
        self.last_frame = IDLE

    def alarm_active(self, now: float) -> bool:
        return now - self.alarm_last <= ALARM_HOLD_S

    def observe(self, scores: dict[str, float], now: float, speaker_role: str = "unknown") -> None:
        """Take one classifier window: {our label: score}."""
        fired = []
        for label, thr in self.threshold.items():
            if scores.get(label, 0.0) >= thr:
                self.hits[label] += 1
            else:
                self.hits[label] = 0
            if self.hits[label] >= self.min_hits.get(label, 1):
                fired.append(label)

        alarms = [l for l in fired if l in L.ALARM_LABELS]
        if alarms:
            if not self.alarm_active(now):
                self.cue_label = None  # an alarm wipes whatever cue was up
            self.alarm_label = max(alarms, key=lambda l: scores[l])
            self.alarm_last = now
            return
        if self.alarm_active(now):
            return  # R2: everything else suppressed while the alarm holds

        cues = [l for l in fired if l in L.CUE_LABELS and self._off_cooldown(l, now)]
        if cues:
            label = max(cues, key=lambda l: scores[l])
            self.cue_label = label
            self.cue_until = now + CUE_TTL_S
            self.cue_started[label] = now

        if "speech" in fired and speaker_role != "self":
            self.speech_last = now

    def name_detected(self, now: float) -> None:
        if not self.alarm_active(now):
            self.name_until = now + NAME_TTL_S

    def _off_cooldown(self, label: str, now: float) -> bool:
        started = self.cue_started.get(label)
        return started is None or now - started >= self.cooldown_s.get(label, 0.0)

    def current(self, now: float, direction: str = "near") -> dict:
        """What the HUD should show right now."""
        if self.alarm_active(now):
            return {"state": "alarm", "label": self.alarm_label, "dir": direction, "ttl_ms": 0, "level": 4}
        if now < self.name_until:
            return {"state": "name", "label": "name", "dir": direction, "ttl_ms": int(NAME_TTL_S * 1000), "level": 4}
        if self.cue_label is not None and now < self.cue_until:
            return {"state": "cue", "label": self.cue_label, "dir": direction, "ttl_ms": int(CUE_TTL_S * 1000), "level": 4}
        if now - self.speech_last <= SPEECH_FADE_S:
            return {"state": "speech", "label": "speech", "dir": direction, "ttl_ms": 0, "level": 2}
        return IDLE

    def step(self, now: float, direction: str = "near") -> dict | None:
        """The new frame if the HUD should change, else None."""
        frame = self.current(now, direction)
        if frame == self.last_frame:
            return None
        self.last_frame = frame
        return frame
