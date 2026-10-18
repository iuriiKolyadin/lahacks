"""YAMNet class names to Earshot labels, and the knobs for when a label counts.

Class names are exactly as they appear in the label list inside the iPhone
app's yamnet.tflite (521 classes). Edit THRESHOLD, MIN_HITS and COOLDOWN_S
at the venue; restart the server to apply.
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
    "Speech": "speech",
    "Child speech, kid speaking": "speech",
    "Conversation": "speech",
    "Narration, monologue": "speech",
}

# Minimum YAMNet score for a window to count as a detection.
THRESHOLD = {
    "doorbell": 0.3,
    "knock": 0.3,
    "siren": 0.3,
    "alarm": 0.3,
    "horn": 0.3,
    "dog": 0.3,
    "speech": 0.5,
}

# Consecutive windows (about 0.5 s each) above threshold before a label fires.
# Raise to 2 if the venue causes false cues; it costs about 0.5 s of latency.
MIN_HITS = {label: 1 for label in THRESHOLD}

# After a cue of a label starts, the same label cannot start a new cue for this
# many seconds. Stops one long doorbell ring from re-flashing every window.
COOLDOWN_S = {
    "doorbell": 5.0,
    "knock": 5.0,
    "horn": 5.0,
    "dog": 5.0,
}

ALARM_LABELS = ("siren", "alarm")
CUE_LABELS = ("doorbell", "knock", "horn", "dog")


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
