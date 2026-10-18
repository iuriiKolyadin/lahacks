# server

The laptop hub. It moves audio from the glasses to the iPhone classifier, turns
the iPhone's YAMNet scores into HUD states.

```
plugin  --/ws/glasses-->  main.py  --/ws/classifier-->  iPhone (audio_classification/ios)
        <---- states ----          <---- results -----
```

## Setup

```bash
cd server
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -r requirements-model.txt   # optional, only for fake_classifier.py --model
```

## Run

```bash
.venv/bin/python main.py            # live
.venv/bin/python main.py --mock     # cycles every HUD state every 5 s
.venv/bin/python test_state.py      # state machine asserts
```

`GET http://LAPTOP_IP:8000/` returns status JSON. The console logs every state
change (`STATE`), every classifier window (`RESULT`, with the round trip and
our labels), and once a second the glasses' `direction` and `speakerRole`
(`TIER0`).

## Captions

With `--stt`, the speech state carries what the person is saying (`text` in
the state frame), and the glasses show it under a `talking` line with the side
arrow. Sounds still win: an alarm, your name or a cue replaces the captions
while it is up. The wearer's own voice (`speakerRole` `self`) is not captioned.
New words count as speech, so captions come up without waiting for YAMNet.

```bash
DEEPGRAM_API_KEY=... .venv/bin/python main.py --stt deepgram   # ~0.5 s behind, needs internet
.venv/bin/pip install -r requirements-stt.txt                    # once, for whisper
.venv/bin/python main.py --stt whisper                         # offline, ~1-2 s behind on a CPU
.venv/bin/python main.py --stt whisper --whisper-model tiny.en # faster, less accurate
```

On Windows: `set DEEPGRAM_API_KEY=...` first, then `.venv\Scripts\python main.py --stt deepgram`.
The first whisper run downloads the model (`base.en` is about 150 MB).

## Without the glasses or the iPhone

```bash
.venv/bin/python fake_classifier.py                 # scripted results, stands in for the iPhone
.venv/bin/python fake_classifier.py --model ../audio_classification/ios/AudioClassification/TFLite/yamnet.tflite
                                                    # real YAMNet on the laptop, same model as the app
.venv/bin/python fake_glasses.py --wav clip.wav     # streams a 16 kHz mono WAV like the plugin
```

## Tuning

`labels.py` holds the YAMNet-to-label map, the score `THRESHOLD` per label,
`HITS` (a label fires only when `needed` of the last `out_of` 0.5 s windows
pass; default 2 of 3, about 1 s of sustained sound), and `COOLDOWN_S` (minimum
gap before the same cue shows again). Timings for the alarm hold,
cue length and speech fade are at the top of `state.py`.

## iPhone app

Open `audio_classification/ios/AudioClassification.xcworkspace` (run
`pod install` there first if `Pods/` is missing), run it on the iPhone, tap the
status text at the top, enter `ws://LAPTOP_IP:8000/ws/classifier`, and pick
"Use glasses audio". Keep it in the foreground and plugged in.
