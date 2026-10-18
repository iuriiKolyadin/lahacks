"""Score the Cue pipeline on saved clips.

For every WAV in the clip folders, this runs the same steps the live system
runs: the high-pass and gain from server/preprocess.py, YAMNet on the last
0.975 s every 0.5 s, the label map and thresholds from server/labels.py, and
the state machine from server/state.py. It reports, per clip, whether the HUD
would have shown the expected label, how long after the clip started, the
best raw score the model gave that label, and anything else that fired.

The expected label is the file name before the first underscore:
doorbell_1.wav expects "doorbell", noise_2.wav expects nothing.
If a .jsonl sidecar from the plugin's recorder sits next to the WAV, the
direction tag is summarised too.

    .venv/bin/python tools/eval.py
    .venv/bin/python tools/eval.py --raw          # skip the high-pass and gain
    .venv/bin/python tools/eval.py --clips plugin/recordings
"""

import argparse
import json
import statistics
import sys
import wave
import zipfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
import direction  # noqa: E402
import labels  # noqa: E402
import preprocess  # noqa: E402
from state import StateMachine  # noqa: E402

WINDOW = 15600
HOP_S = 0.5
RATE = 16000
DEFAULT_MODEL = ROOT / "audio_classification/ios/AudioClassification/TFLite/yamnet.tflite"
DEFAULT_CLIPS = [ROOT / "server/clips", ROOT / "plugin/recordings"]
ALARM = set(labels.ALARM_LABELS)


class Yamnet:
    def __init__(self, path: Path):
        from ai_edge_litert.interpreter import Interpreter

        self.names = zipfile.ZipFile(path).read("yamnet_label_list.txt").decode().splitlines()
        self.interp = Interpreter(model_path=str(path))
        inp = self.interp.get_input_details()[0]
        self.interp.allocate_tensors()
        self.inp, self.shape = inp["index"], inp["shape"]
        self.out = self.interp.get_output_details()[0]["index"]

    def scores(self, window: np.ndarray) -> dict[str, float]:
        x = np.zeros(WINDOW, dtype=np.float32)
        x[WINDOW - len(window):] = window[-WINDOW:]
        self.interp.set_tensor(self.inp, x.reshape(self.shape))
        self.interp.invoke()
        s = self.interp.get_tensor(self.out).reshape(-1, len(self.names)).mean(axis=0)
        return {self.names[i]: float(s[i]) for i in np.argsort(s)[::-1][:10]}


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        assert w.getframerate() == RATE and w.getnchannels() == 1 and w.getsampwidth() == 2, path
        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float64) / 32768.0


def expected_of(path: Path) -> str | None:
    head = path.stem.split("_")[0].lower()
    return head if head in labels.THRESHOLD else None


def run_clip(model: Yamnet, audio: np.ndarray, raw: bool, hpf: float | None = None, gain: bool = True, dual: bool = False):
    """Yield (t, our_scores, top_name, top_score, hud_frame_or_None) every hop."""
    original = audio
    if not raw:
        fc = preprocess.HPF_HZ if hpf is None else hpf
        if fc > 0:
            audio = preprocess.HighPass(fc=fc)(audio)
    sm = StateMachine()
    n_hops = int(np.ceil(len(audio) / (HOP_S * RATE)))
    for h in range(1, n_hops + 1):
        end = min(len(audio), int(h * HOP_S * RATE))
        t = end / RATE
        win = audio[max(0, end - WINDOW):end]
        if not raw and gain:
            win = preprocess.normalize(win)
        top = model.scores(win)
        if dual:
            raw_win = original[max(0, end - WINDOW):end]
            for k, v in model.scores(raw_win).items():
                top[k] = max(top.get(k, 0.0), v)
            top = dict(sorted(top.items(), key=lambda kv: -kv[1]))
        name, score = next(iter(top.items()))
        ours = labels.scores_by_label([{"label": k, "score": v} for k, v in top.items()])
        sm.observe(ours, t)
        yield t, ours, name, score, sm.step(t)


def shown_label(frame) -> str | None:
    if not frame or frame.get("state") in (None, "idle"):
        return None
    return frame.get("label")


def summarise_direction(jsonl: Path) -> str:
    tr = direction.DirectionTracker()
    tags = []
    for line in jsonl.open():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("direction") is not None:
            tags.append(d["direction"])
            tr.add(d["direction"], float(d.get("rms", 1.0)), now=float(d.get("ts", 0)) / 1000)
    if not tags:
        return "direction: always null"
    ang = statistics.median(tags)
    return f"direction: median {ang:+.0f} deg, range {min(tags)}..{max(tags)} -> {direction.side_from_angle(ang)}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    ap.add_argument("--clips", type=Path, nargs="*", default=DEFAULT_CLIPS)
    ap.add_argument("--raw", action="store_true", help="skip the high-pass and gain")
    ap.add_argument("--hpf", type=float, default=None, help="high-pass cutoff in Hz (default: server's value, 0 = none)")
    ap.add_argument("--no-gain", action="store_true", help="keep the high-pass but skip the per-window gain")
    ap.add_argument("--dual", action="store_true",
                    help="run the model on both the raw and the filtered window and keep the higher score per label")
    ap.add_argument("--verbose", action="store_true", help="print every window")
    args = ap.parse_args()

    model = Yamnet(args.model)
    files = sorted(p for d in args.clips if d.exists() for p in d.glob("*.wav"))
    if not files:
        sys.exit("no clips found")

    fc = 0 if args.raw else (preprocess.HPF_HZ if args.hpf is None else args.hpf)
    print(f"model {args.model.name}, high-pass {fc:g} Hz, gain {'off' if (args.raw or args.no_gain) else 'on'}, "
          f"dual {'on' if args.dual else 'off'}, hop {HOP_S}s\n")
    print(f"{'clip':<30} {'expect':<9} {'shown':<9} {'first at':>8} {'best score':>10}  other labels shown / top raw class")
    rows = []
    for path in files:
        audio = read_wav(path)
        if len(audio) < RATE * 0.5:
            print(f"{path.parent.name}/{path.name:<22} (empty, skipped)")
            continue
        expect = expected_of(path)
        first_at = None
        best = 0.0
        shown = []
        top_classes = {}
        for t, ours, name, score, frame in run_clip(model, audio, args.raw, args.hpf, not args.no_gain, args.dual):
            if expect:
                best = max(best, ours.get(expect, 0.0))
            lab = shown_label(frame)
            if lab:
                shown.append(lab)
                same_tier = expect in ALARM and lab in ALARM
                if (lab == expect or same_tier) and first_at is None:
                    first_at = t
            top_classes[name] = max(top_classes.get(name, 0.0), score)
            if args.verbose:
                mine = " ".join(f"{k}={v:.2f}" for k, v in ours.items())
                print(f"   {t:5.1f}s  {name}:{score:.2f}  {mine or '-'}  {'-> ' + json.dumps(frame) if frame else ''}")
        others = sorted(set(l for l in shown if l != expect and not (expect in ALARM and l in ALARM)))
        top3 = sorted(top_classes.items(), key=lambda kv: -kv[1])[:3]
        hit = first_at is not None
        status = (first_at and f"{first_at:5.1f}s") or ("ok" if expect is None and not shown else "MISS")
        if expect is None and shown:
            status = "FALSE"
        shown_name = f"{path.parent.name}/{path.name}"
        print(f"{shown_name:<30} {expect or '-':<9} {(shown[0] if shown else '-'):<9} {status:>8} {best:>10.2f}  "
              f"{','.join(others) or '-'} / {', '.join(f'{k} {v:.2f}' for k, v in top3)}")
        side = path.with_suffix(".jsonl")
        if side.exists():
            print(f"{'':<30} {summarise_direction(side)}")
        rows.append((expect, hit, first_at, others, len(shown)))

    print("\nper class")
    print(f"{'class':<10} {'clips':>5} {'shown':>5} {'median first at':>16}")
    for cls in sorted({r[0] for r in rows if r[0]}):
        mine = [r for r in rows if r[0] == cls]
        hits = [r[2] for r in mine if r[1]]
        med = f"{statistics.median(hits):.1f}s" if hits else "-"
        print(f"{cls:<10} {len(mine):>5} {len(hits):>5} {med:>16}")
    noise = [r for r in rows if r[0] is None]
    if noise:
        false = sum(1 for r in noise if r[4])
        print(f"\nnoise clips: {len(noise)}, with a false cue: {false}")
    wrong = sum(1 for r in rows if r[0] and r[3])
    print(f"clips that also showed a wrong label: {wrong} of {sum(1 for r in rows if r[0])}")


if __name__ == "__main__":
    main()
