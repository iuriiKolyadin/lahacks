"""python -m pytest test_state.py  (or just: python test_state.py)"""

import state
from state import IDLE

# Most tests check the priority and timing rules on single windows, so they use
# 1-of-1 and a 0.3 threshold everywhere; the k-of-n rule has its own tests.
ANY = {l: (1, 1) for l in ("doorbell", "knock", "siren", "alarm", "horn", "dog", "clap", "snap", "speech")}
LOW = {l: 0.3 for l in ANY} | {"speech": 0.5}


def StateMachine(**kw):
    kw.setdefault("hits", ANY)
    kw.setdefault("threshold", LOW)
    return state.StateMachine(**kw)


def test_doorbell_shows_then_clears():
    sm = StateMachine()
    sm.observe({"doorbell": 0.8}, now=0.0)
    assert sm.step(0.0)["label"] == "doorbell"
    assert sm.step(3.9) is None
    assert sm.step(4.1) == IDLE


def test_below_threshold_shows_nothing():
    sm = StateMachine()
    sm.observe({"doorbell": 0.1, "speech": 0.4}, now=0.0)
    assert sm.step(0.0) is None


def test_two_sounds_at_once_picks_higher():
    sm = StateMachine()
    sm.observe({"doorbell": 0.5, "dog": 0.9}, now=0.0)
    assert sm.step(0.0)["label"] == "dog"


def test_alarm_suppresses_doorbell_and_holds():
    sm = StateMachine()
    sm.observe({"siren": 0.7, "doorbell": 0.9}, now=0.0)
    assert sm.step(0.0)["state"] == "alarm"
    sm.observe({"doorbell": 0.9}, now=1.0)  # siren stopped, doorbell still ringing
    assert sm.current(1.0)["state"] == "alarm"
    assert sm.current(3.5) == IDLE  # doorbell during the hold was dropped


def test_alarm_then_doorbell_after_hold():
    sm = StateMachine()
    sm.observe({"alarm": 0.7}, now=0.0)
    sm.observe({"doorbell": 0.9}, now=3.5)
    assert sm.current(3.5)["label"] == "doorbell"


def test_alarm_wipes_existing_cue():
    sm = StateMachine()
    sm.observe({"knock": 0.9}, now=0.0)
    sm.observe({"siren": 0.9}, now=0.5)
    assert sm.current(3.6) == IDLE  # 3.1 s after the siren; knock did not come back


def test_speech_from_self_ignored():
    sm = StateMachine()
    sm.observe({"speech": 0.9}, now=0.0, speaker_role="self")
    assert sm.step(0.0) is None
    sm.observe({"speech": 0.9}, now=1.0, speaker_role="other")
    assert sm.step(1.0)["state"] == "speech"
    assert sm.current(3.9)["state"] == "speech"
    assert sm.current(4.1) == IDLE


def test_cue_beats_speech():
    sm = StateMachine()
    sm.observe({"speech": 0.9, "knock": 0.6}, now=0.0)
    assert sm.current(0.0)["label"] == "knock"
    assert sm.current(2.0)["label"] == "knock"
    assert sm.current(4.5) == IDLE  # speech at t=0 had faded by the time the knock ended


def test_cooldown_blocks_repeat_of_same_label():
    sm = StateMachine()
    sm.observe({"doorbell": 0.9}, now=0.0)
    sm.observe({"doorbell": 0.9}, now=4.5)  # inside the 5 s cooldown
    assert sm.current(4.5) == IDLE
    sm.observe({"doorbell": 0.9}, now=5.5)
    assert sm.current(5.5)["label"] == "doorbell"


def test_newer_cue_replaces_older():
    sm = StateMachine()
    sm.observe({"doorbell": 0.9}, now=0.0)
    sm.observe({"dog": 0.9}, now=1.0)
    assert sm.current(1.0)["label"] == "dog"
    assert sm.current(4.5)["label"] == "dog"


def test_two_of_three_drops_a_single_blip():
    sm = StateMachine(hits={"doorbell": (2, 3)})
    sm.observe({"doorbell": 0.9}, now=0.0)
    assert sm.current(0.0) == IDLE
    sm.observe({}, now=0.5)
    sm.observe({}, now=1.0)
    sm.observe({"doorbell": 0.9}, now=1.5)  # the first hit has left the window
    assert sm.current(1.5) == IDLE


def test_two_of_three_fires_with_a_gap():
    sm = StateMachine(hits={"doorbell": (2, 3)})
    sm.observe({"doorbell": 0.9}, now=0.0)
    sm.observe({}, now=0.5)
    sm.observe({"doorbell": 0.9}, now=1.0)
    assert sm.current(1.0)["label"] == "doorbell"


def test_fires_on_a_window_where_the_label_is_missing():
    sm = StateMachine(hits={"siren": (2, 3), "doorbell": (2, 3)})
    sm.observe({"siren": 0.9}, now=0.0)
    sm.observe({"siren": 0.9}, now=0.5)
    sm.observe({}, now=1.0)  # still 2 of the last 3; used to raise KeyError
    assert sm.current(1.0)["state"] == "alarm"
    sm2 = StateMachine(hits={"doorbell": (2, 3)})
    sm2.observe({"doorbell": 0.9}, now=0.0)
    sm2.observe({"doorbell": 0.9}, now=0.5)
    sm2.observe({}, now=1.0)
    assert sm2.current(1.0)["label"] == "doorbell"


def test_single_bark_fires_with_defaults():
    sm = state.StateMachine()  # the real labels.py settings
    sm.observe({"dog": 0.45}, now=0.0)  # one short bark, one window
    assert sm.current(0.0)["label"] == "dog"
    sm2 = state.StateMachine()
    sm2.observe({"dog": 0.35}, now=0.0)  # below 0.4
    assert sm2.current(0.0) == IDLE


def test_defaults_ignore_noise_but_keep_alarms():
    sm = state.StateMachine()  # the real labels.py settings
    for t in (0.0, 0.5, 1.0):
        sm.observe({"doorbell": 0.45, "speech": 0.55}, now=t)  # below the strict thresholds
    assert sm.current(1.0) == IDLE
    sm.observe({"alarm": 0.35}, now=1.5)
    sm.observe({"alarm": 0.32}, now=2.0)
    assert sm.current(2.0)["state"] == "alarm"


def test_name_beats_cue_but_not_alarm():
    sm = StateMachine()
    sm.observe({"knock": 0.9}, now=0.0)
    sm.name_detected(now=0.5)
    assert sm.current(0.5)["state"] == "name"
    sm.observe({"siren": 0.9}, now=1.0)
    assert sm.current(1.0)["state"] == "alarm"


def test_cue_keeps_its_starting_direction():
    sm = StateMachine()
    sm.observe({"knock": 0.9}, now=0.0, direction="left")
    sm.observe({}, now=0.5, direction="right")  # room noise from elsewhere while the cue is up
    assert sm.current(1.0)["dir"] == "left"


def test_alarm_direction_ignores_one_off_flips():
    sm = StateMachine()
    sm.observe({"siren": 0.9}, now=0.0, direction="left")
    sm.observe({"siren": 0.9}, now=0.5, direction="left")
    sm.observe({"siren": 0.9}, now=1.0, direction="near")  # one jittery reading
    assert sm.current(1.0)["dir"] == "left"
    sm.observe({"siren": 0.9}, now=1.5, direction="right")
    sm.observe({"siren": 0.9}, now=2.0, direction="right")  # the source really moved
    assert sm.current(2.0)["dir"] == "right"


def test_snap_and_clap_are_cues():
    sm = StateMachine()
    sm.observe({"snap": 0.8}, now=0.0)
    assert sm.current(0.0)["label"] == "snap"
    sm.observe({"clap": 0.9}, now=1.0)
    assert sm.current(1.0)["label"] == "clap"


def test_direction_sides_and_center():
    import direction as D
    assert D.side_from_angle(None) == "near"
    assert D.side_from_angle(0) == D.CENTER == "center"
    assert D.side_from_angle(D.SIDE_DEG * D.SIGN) == "right"
    assert D.side_from_angle(-D.SIDE_DEG * D.SIGN) == "left"


def test_direction_uses_loud_recent_frames():
    import direction as D
    tr = D.DirectionTracker()
    for i in range(10):  # quiet room frames at 0 deg
        tr.add(0, rms=10, now=i * 0.06)
    for i in range(10):  # the loud sound at -66 deg
        tr.add(-66, rms=500, now=0.6 + i * 0.03)
    assert tr.angle(now=0.9) == -66
    assert tr.angle(now=9.0) is None  # all frames older than the window


def test_direction_transient_beats_room_noise():
    # A snap as the G2 really reports it (snap #8 in docs/direction-test.md):
    # the tag lands one frame BEFORE the loud audio, and the tag on the loud
    # frame itself is junk. 60 room frames, then the snap, and the classifier
    # result lands 1.5 s later. The snap's own tag (+49, left) must win.
    import direction as D
    tr = D.DirectionTracker()
    for i in range(60):
        tr.add(-17, rms=600, now=i * 0.05)
    tr.add(49, rms=95, now=1.0)      # tag for the snap, audio not here yet
    tr.add(-66, rms=1778, now=1.05)  # the snap's audio, with a junk tag
    tr.add(-90, rms=729, now=1.1)
    for i in range(30):
        tr.add(-8, rms=600, now=1.15 + i * 0.05)
    assert tr.angle(now=2.5) == 49
    assert tr.side(now=2.5) == "left"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
