"""Fake Earshot server for plugin development.

Sends one HUD state from PLAN.md section 3 every 4 s, and prints a once-per-second
summary of the audio frames the plugin sends up (frames/s, RMS, direction, speakerRole).

    pip install websockets
    python fake_server.py
"""
import asyncio, base64, itertools, json, math, struct, time

from websockets.asyncio.server import serve

STATES = [
    {"state": "idle"},
    {"state": "cue", "label": "doorbell", "dir": "right", "ttl_ms": 4000, "level": 4},
    {"state": "cue", "label": "knock", "dir": "behind", "ttl_ms": 4000, "level": 4},
    {"state": "speech", "label": "speech", "dir": "left", "ttl_ms": 0, "level": 2},
    {"state": "name", "label": "name", "dir": "left", "ttl_ms": 4000, "level": 4},
    {"state": "alarm", "label": "siren", "dir": "behind", "ttl_ms": 0, "level": 4},
    {"state": "cue", "label": "dog", "dir": "near", "ttl_ms": 4000, "level": 4},
]


async def send_states(ws):
    for s in itertools.cycle(STATES):
        await ws.send(json.dumps(s))
        print("->", s)
        await asyncio.sleep(4)


async def handler(ws):
    print("plugin connected:", ws.remote_address, ws.request.path)
    sender = asyncio.create_task(send_states(ws))
    frames, sq, n, last, t0 = 0, 0.0, 0, None, time.time()
    try:
        async for msg in ws:
            f = json.loads(msg)
            pcm = base64.b64decode(f.get("pcm", ""))
            samples = struct.unpack(f"<{len(pcm) // 2}h", pcm[: len(pcm) // 2 * 2])
            frames, n, sq = frames + 1, n + len(samples), sq + sum(x * x for x in samples)
            last = (f.get("direction"), f.get("speakerRole"))
            if time.time() - t0 >= 1:
                rms = math.sqrt(sq / n) if n else 0
                print(f"<- {frames} frames/s  rms={rms:6.0f}  direction={last[0]}  speakerRole={last[1]}")
                frames, sq, n, t0 = 0, 0.0, 0, time.time()
    finally:
        sender.cancel()
        print("plugin disconnected")


async def main():
    async with serve(handler, "0.0.0.0", 8000) as server:
        print("fake server on ws://0.0.0.0:8000/ws/glasses")
        await server.serve_forever()


asyncio.run(main())
