"""Fake Cue server for plugin development.

Sends one HUD state from PRD.md section 5 every 4 s, and prints a once-per-second
summary of the audio frames the plugin sends up (frames/s, RMS, direction, speakerRole).

    pip install websockets
    python fake_server.py
    python fake_server.py --save recordings/alarm    # also writes alarm_1.wav (+ .jsonl) per connection
"""
import argparse, asyncio, base64, itertools, json, math, os, statistics, struct, time, wave
from collections import Counter

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


conn_ids = itertools.count(1)
open_conns = set()


async def send_states(ws, cid):
    for s in itertools.cycle(STATES):
        await ws.send(json.dumps(s))
        print(f"[#{cid}] ->", s)
        await asyncio.sleep(4)


async def handler(ws):
    cid = next(conn_ids)
    open_conns.add(cid)
    print(f"[#{cid}] plugin connected: {ws.remote_address} {ws.request.path}  (open: {sorted(open_conns)})")
    sender = asyncio.create_task(send_states(ws, cid))
    frames, sq, n, t0 = 0, 0.0, 0, time.time()
    roles, dirs = Counter(), []
    wav = meta = None
    if args.save:
        os.makedirs(os.path.dirname(args.save) or ".", exist_ok=True)
        wav = wave.open(f"{args.save}_{cid}.wav", "wb")
        wav.setnchannels(1), wav.setsampwidth(2), wav.setframerate(16000)
        meta = open(f"{args.save}_{cid}.jsonl", "w")
        print(f"[#{cid}] recording to {args.save}_{cid}.wav")
    try:
        async for msg in ws:
            f = json.loads(msg)
            pcm = base64.b64decode(f.get("pcm", ""))
            samples = struct.unpack(f"<{len(pcm) // 2}h", pcm[: len(pcm) // 2 * 2])
            if wav:
                wav.writeframes(pcm[: len(samples) * 2])
                rms_f = math.sqrt(sum(x * x for x in samples) / len(samples)) if samples else 0
                meta.write(json.dumps({"ts": f.get("ts"), "direction": f.get("direction"),
                                       "speakerRole": f.get("speakerRole"), "rms": round(rms_f)}) + "\n")
            frames, n, sq = frames + 1, n + len(samples), sq + sum(x * x for x in samples)
            roles[f.get("speakerRole")] += 1
            if f.get("direction") is not None:
                dirs.append(f["direction"])
            if time.time() - t0 >= 1:
                rms = math.sqrt(sq / n) if n else 0
                d = f"{statistics.median(dirs):5.0f}" if dirs else " null"
                print(f"[#{cid}] <- {frames:2} frames  {n:5} samples/s  rms={rms:5.0f}  "
                      f"dir median={d}  self={roles['self']:2} other={roles['other']:2} unknown={roles['unknown']:2}")
                frames, sq, n, t0 = 0, 0.0, 0, time.time()
                roles, dirs = Counter(), []
    finally:
        sender.cancel()
        if wav:
            wav.close(), meta.close()
            print(f"[#{cid}] saved {args.save}_{cid}.wav")
        open_conns.discard(cid)
        print(f"[#{cid}] plugin disconnected  (open: {sorted(open_conns)})")


async def main():
    async with serve(handler, "0.0.0.0", args.port) as server:
        print(f"fake server on ws://0.0.0.0:{args.port}/ws/glasses")
        await server.serve_forever()


ap = argparse.ArgumentParser()
ap.add_argument("--save", help="path prefix; writes <prefix>_<conn>.wav (16 kHz mono) and .jsonl per connection")
ap.add_argument("--port", type=int, default=8000)
args = ap.parse_args()
asyncio.run(main())
