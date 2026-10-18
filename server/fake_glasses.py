"""Pretends to be the plugin: streams a WAV (or silence) to /ws/glasses in real
time, in the PLAN.md section 3 format, and prints every HUD state it gets back.

    python fake_glasses.py --wav clips/doorbell_1.wav
    python fake_glasses.py                      # silence, forever
    python fake_glasses.py --say repeat         # also send one say frame
    python fake_glasses.py --seconds 20         # stop after 20 s
    python fake_glasses.py --role self          # mark audio as the wearer's own voice

The WAV must be 16 kHz mono 16-bit:  ffmpeg -i in.mp3 -ar 16000 -ac 1 out.wav
"""

import argparse
import asyncio
import base64
import json
import time
import wave

from websockets.asyncio.client import connect

RATE = 16000
CHUNK = 1600  # 100 ms per frame


def chunks(path: str | None, loop: bool):
    if path is None:
        while True:
            yield b"\x00\x00" * CHUNK
    with wave.open(path, "rb") as w:
        assert w.getframerate() == RATE and w.getnchannels() == 1 and w.getsampwidth() == 2, (
            f"{path} must be 16 kHz mono 16-bit, got {w.getframerate()} Hz, "
            f"{w.getnchannels()} ch, {8 * w.getsampwidth()} bit"
        )
        data = w.readframes(w.getnframes())
    while True:
        for i in range(0, len(data), CHUNK * 2):
            yield data[i : i + CHUNK * 2]
        if not loop:
            break
    for _ in range(30):  # 3 s of silence after the clip so states can clear
        yield b"\x00\x00" * CHUNK


async def run(args):
    async with connect(args.url, max_size=None) as ws:
        print("connected", args.url)
        t0 = time.time()

        async def reader():
            async for msg in ws:
                print(f"{time.time() - t0:6.2f}s  STATE {msg}")

        read = asyncio.create_task(reader())
        if args.say:
            await ws.send(json.dumps({"t": "say", "phrase": args.say}))
            print("sent say", args.say)
        start = time.time()
        for n, pcm in enumerate(chunks(args.wav, args.loop)):
            if args.seconds and time.time() - start > args.seconds:
                break
            frame = {
                "t": "audio",
                "pcm": base64.b64encode(pcm).decode(),
                "direction": args.direction,
                "speakerRole": args.role,
                "ts": int(time.time() * 1000),
            }
            await ws.send(json.dumps(frame))
            # pace to real time against the start, so drift does not build up
            await asyncio.sleep(max(0.0, start + (n + 1) * CHUNK / RATE - time.time()))
        await asyncio.sleep(1)
        read.cancel()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="ws://localhost:8000/ws/glasses")
    ap.add_argument("--wav")
    ap.add_argument("--loop", action="store_true", help="repeat the WAV forever")
    ap.add_argument("--say", choices=["deaf_intro", "repeat", "type_it"])
    ap.add_argument("--role", default="other", choices=["self", "other", "unknown"])
    ap.add_argument("--direction", type=int, default=None)
    ap.add_argument("--seconds", type=float, help="stop after this long")
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
