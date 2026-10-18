"""python -m pytest test_state.py  (or just: python test_state.py)"""

from state import StateMachine, IDLE


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
    assert sm.current(2.5) == IDLE  # doorbell during the hold was dropped


def test_alarm_then_doorbell_after_hold():
    sm = StateMachine()
    sm.observe({"alarm": 0.7}, now=0.0)
    sm.observe({"doorbell": 0.9}, now=3.0)
    assert sm.current(3.0)["label"] == "doorbell"


def test_alarm_wipes_existing_cue():
    sm = StateMachine()
    sm.observe({"knock": 0.9}, now=0.0)
    sm.observe({"siren": 0.9}, now=0.5)
    assert sm.current(3.0) == IDLE  # 2.5 s after the siren; knock did not come back


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


def test_min_hits_needs_consecutive_windows():
    sm = StateMachine(min_hits={"doorbell": 2})
    sm.observe({"doorbell": 0.9}, now=0.0)
    assert sm.current(0.0) == IDLE
    sm.observe({"doorbell": 0.9}, now=0.5)
    assert sm.current(0.5)["label"] == "doorbell"


def test_name_beats_cue_but_not_alarm():
    sm = StateMachine()
    sm.observe({"knock": 0.9}, now=0.0)
    sm.name_detected(now=0.5)
    assert sm.current(0.5)["state"] == "name"
    sm.observe({"siren": 0.9}, now=1.0)
    assert sm.current(1.0)["state"] == "alarm"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
