"""Stands in for the iPhone YAMNet app on /ws/classifier.

Two modes:
    python fake_classifier.py
        Scripted. While audio is arriving, sends a result every 0.5 s that cycles
        quiet, doorbell, quiet, speech, siren, so the whole loop can be tested
        without the iPhone.
    python fake_classifier.py --model
        Real, and a full replacement for the iPhone on Windows, macOS or Linux.
        Runs the same yamnet.tflite the iPhone app ships (default path below, or
        --model PATH) on the audio it receives, the same way the app does
        (high-pass and gain from preprocess.py, last 15600 samples every 0.5 s).
        Needs `pip install -r requirements-model.txt`. `main.py --classify` starts
        it for you. Also handy with fake_glasses.py --wav to tune labels.py.

Reconnects every second until stopped, so it can start before the server.
"""

import argparse
import asyncio
import base64
import json
import os
import time
import zipfile

from websockets.asyncio.client import connect

# The model the iPhone app ships; it carries its own label list.
MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "audio_classification", "ios",
                     "AudioClassification", "TFLite", "yamnet.tflite")
WINDOW = 15600
HOP_S = 0.5
SCRIPT = (
    [("Silence", 0.9)] * 6
    + [("Doorbell", 0.82)] * 2
    + [("Silence", 0.9)] * 6
    + [("Speech", 0.75)] * 6
    + [("Silence", 0.9)] * 6
    + [("Siren", 0.7)] * 4
    + [("Silence", 0.9)] * 8
)


class Yamnet:
    def __init__(self, path: str):
        import numpy as np
        from ai_edge_litert.interpreter import Interpreter

        self.np = np
        self.names = zipfile.ZipFile(path).read("yamnet_label_list.txt").decode().splitlines()
        self.interp = Interpreter(model_path=path)
        inp = self.interp.get_input_details()[0]
        self.interp.allocate_tensors()
        self.inp, self.shape = inp["index"], inp["shape"]  # [15600] or [1, 15600]
        self.out = self.interp.get_output_details()[0]["index"]

    def top(self, samples, k: int = 10, filtered: bool = False):
        """`samples` is int16 LE bytes. Pass filtered=True if they already went through HighPass."""
        import preprocess

        np = self.np
        x = np.zeros(WINDOW, dtype=np.float32)
        tail = np.frombuffer(bytes(samples[-WINDOW * 2 :]), dtype="<i2").astype(np.float64) / 32768.0
        if filtered:
            tail = preprocess.normalize(tail)
        x[WINDOW - len(tail) :] = tail
        self.interp.set_tensor(self.inp, x.reshape(self.shape))
        self.interp.invoke()
        scores = self.interp.get_tensor(self.out).reshape(-1, len(self.names)).mean(axis=0)
        best = np.argsort(scores)[::-1][:k]
        return [{"label": self.names[i], "score": round(float(scores[i]), 3)} for i in best]


async def run(args):
    model = Yamnet(args.model) if args.model else None
    while True:
        try:
            await session(args, model)
            print("disconnected; retrying in 1 s", flush=True)
        except Exception as err:  # refused, handshake rejected, dropped mid-session
            print(f"cannot reach {args.url} ({err!r}); retrying in 1 s", flush=True)
        await asyncio.sleep(1)


async def session(args, model):
    hp = None
    if model and not args.raw:
        import numpy as np
        import preprocess

        hp = preprocess.HighPass()
    async with connect(args.url, max_size=None) as ws:
        print("connected", args.url, "real YAMNet" if model else "scripted", flush=True)
        buf = bytearray()
        state = {"ts": None, "at": 0.0}

        async def reader():
            async for raw in ws:
                msg = json.loads(raw)
                if msg.get("t") != "audio":
                    continue
                pcm = base64.b64decode(msg["pcm"])
                if hp:
                    x = np.frombuffer(pcm, dtype="<i2").astype(np.float64) / 32768.0
                    pcm = (np.clip(hp(x), -1, 1) * 32767).astype("<i2").tobytes()
                buf.extend(pcm)
                del buf[: max(0, len(buf) - WINDOW * 2)]
                state["ts"], state["at"] = msg.get("ts"), time.time()

        read = asyncio.create_task(reader())
        script = iter(SCRIPT * 1000)
        last_sent_ts = None
        while not read.done():
            await asyncio.sleep(HOP_S)
            if state["ts"] is None or state["ts"] == last_sent_ts or time.time() - state["at"] > 1.0:
                continue  # no fresh audio: send nothing, like the app
            last_sent_ts = state["ts"]
            t = time.time()
            if model:
                top = model.top(buf, filtered=hp is not None)
            else:
                label, score = next(script)
                top = [{"label": label, "score": score}, {"label": "Music", "score": 0.05}]
            result = {"t": "result", "ts": state["ts"], "inference_ms": int((time.time() - t) * 1000), "top": top}
            try:
                await ws.send(json.dumps(result))
            except Exception:
                break  # socket closed; run() reconnects
            if not args.quiet:
                print("->", " ".join(f"{c['label']}:{c['score']:.2f}" for c in top[:3]), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="ws://localhost:8000/ws/classifier")
    ap.add_argument("--model", nargs="?", const=MODEL,
                    help="real classification with yamnet.tflite (default: the one the iPhone app ships)")
    ap.add_argument("--raw", action="store_true", help="with --model: skip the high-pass and gain")
    ap.add_argument("--quiet", action="store_true", help="do not print every result (the server logs them)")
    try:
        asyncio.run(run(ap.parse_args()))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
