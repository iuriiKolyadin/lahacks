"""Pretends to be the iPhone YAMNet app on /ws/classifier.

Two modes:
    python fake_classifier.py
        Scripted. While audio is arriving, sends a result every 0.5 s that cycles
        quiet, doorbell, quiet, speech, siren, so the whole loop can be tested
        without the iPhone.
    python fake_classifier.py --model ../audio_classification/ios/AudioClassification/TFLite/yamnet.tflite
        Real. Runs the same yamnet.tflite the iPhone app ships on the audio it
        receives, the same way the app does (last 15600 samples every 0.5 s).
        Needs `pip install ai-edge-litert`. Use it with fake_glasses.py --wav to
        tune thresholds in labels.py without the phone.
"""

import argparse
import asyncio
import base64
import json
import time
import zipfile

from websockets.asyncio.client import connect

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

    def top(self, samples, k: int = 10):
        np = self.np
        x = np.zeros(WINDOW, dtype=np.float32)
        tail = np.frombuffer(bytes(samples[-WINDOW * 2 :]), dtype="<i2").astype(np.float32) / 32768.0
        x[WINDOW - len(tail) :] = tail
        self.interp.set_tensor(self.inp, x.reshape(self.shape))
        self.interp.invoke()
        scores = self.interp.get_tensor(self.out).reshape(-1, len(self.names)).mean(axis=0)
        best = np.argsort(scores)[::-1][:k]
        return [{"label": self.names[i], "score": round(float(scores[i]), 3)} for i in best]


async def run(args):
    model = Yamnet(args.model) if args.model else None
    async with connect(args.url, max_size=None) as ws:
        print("connected", args.url, "real YAMNet" if model else "scripted")
        buf = bytearray()
        state = {"ts": None, "at": 0.0}

        async def reader():
            async for raw in ws:
                msg = json.loads(raw)
                if msg.get("t") != "audio":
                    continue
                buf.extend(base64.b64decode(msg["pcm"]))
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
                top = model.top(buf)
            else:
                label, score = next(script)
                top = [{"label": label, "score": score}, {"label": "Music", "score": 0.05}]
            result = {"t": "result", "ts": state["ts"], "inference_ms": int((time.time() - t) * 1000), "top": top}
            await ws.send(json.dumps(result))
            print("->", " ".join(f"{c['label']}:{c['score']:.2f}" for c in top[:3]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="ws://localhost:8000/ws/classifier")
    ap.add_argument("--model", help="path to yamnet.tflite for real classification")
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
