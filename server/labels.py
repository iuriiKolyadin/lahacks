"""YAMNet class names to Earshot labels, and the knobs for when a label counts.

Class names are exactly as they appear in the label list inside the iPhone
app's yamnet.tflite (521 classes). Edit THRESHOLD, HITS and COOLDOWN_S at
the venue; restart the server to apply.
"""

YAMNET_TO_LABEL = {
    "Doorbell": "doorbell",
    "Ding-dong": "doorbell",
    "Knock": "knock",
    "Siren": "siren",
    "Civil defense siren": "siren",
    "Police car (siren)": "siren",
    "Ambulance (siren)": "siren",
    "Fire engine, fire truck (siren)": "siren",
    "Alarm": "alarm",
    "Smoke detector, smoke alarm": "alarm",
    "Fire alarm": "alarm",
    "Car alarm": "alarm",
    "Alarm clock": "alarm",
    "Vehicle horn, car horn, honking": "horn",
    "Air horn, truck horn": "horn",
    "Dog": "dog",
    "Bark": "dog",
    "Bow-wow": "dog",
    "Yip": "dog",
    "Howl": "dog",
    "Growling": "dog",
    "Whimper (dog)": "dog",
    "Clapping": "clap",
    "Finger snapping": "snap",
    "Speech": "speech",
    "Child speech, kid speaking": "speech",
    "Conversation": "speech",
    "Narration, monologue": "speech",
}

# Minimum YAMNet score for a window to count as a detection.
# Alarm and siren stay at 0.3: through the G2 mic a real smoke alarm peaks at
# only 0.3 to 0.5 even after preprocessing (plugin/recordings/alarm_1.wav),
# and a missed alarm is the worst failure. Everything else is strict so room
# noise does not reach the HUD.
THRESHOLD = {
    "doorbell": 0.5,
    "knock": 0.5,
    "siren": 0.3,
    "alarm": 0.3,
    "horn": 0.5,
    "dog": 0.5,
    "clap": 0.5,
    "snap": 0.5,
    "speech": 0.6,
}

# (needed, out_of): a label fires only when `needed` of the last `out_of`
# windows are above threshold. Windows are 0.5 s apart, so (2, 3) means about
# 1 s of sustained sound; one-off blips are dropped. (1, 1) fires on any window.
# Alarm and siren use (2, 4): through the G2 mic a real alarm is detected on and
# off, and with 2 of 3 ALARM came on late and blinked off once; with 2 of 4 it
# held from 2.5 s to the end of alarm_1.wav.
HITS = {label: (2, 3) for label in THRESHOLD} | {"siren": (2, 4), "alarm": (2, 4)}

# After a cue of a label starts, the same label cannot start a new cue for this
# many seconds. Stops one long doorbell ring from re-flashing every window.
COOLDOWN_S = {
    "doorbell": 5.0,
    "knock": 5.0,
    "horn": 5.0,
    "dog": 5.0,
    "clap": 3.0,
    "snap": 3.0,
}

ALARM_LABELS = ("siren", "alarm")
CUE_LABELS = ("doorbell", "knock", "horn", "dog", "clap", "snap")


def scores_by_label(top: list[dict]) -> dict[str, float]:
    """Collapse YAMNet categories to our labels, keeping the best score per label.

    `top` is the classifier's list of {"label": <YAMNet name>, "score": float}.
    Classes we do not care about are dropped.
    """
    out: dict[str, float] = {}
    for cat in top:
        label = YAMNET_TO_LABEL.get(cat.get("label", ""))
        if label is not None:
            out[label] = max(out.get(label, 0.0), float(cat.get("score", 0.0)))
    return out
