"""Earshot hub: glasses <-> iPhone classifier, plus the pendant relay.

    python main.py            # real: needs the plugin and the iPhone classifier
    python main.py --mock     # cycles every HUD state every 5 s, no classifier

Sockets (all on port 8000):
  /ws/glasses     the plugin. Sends audio and say frames (PLAN.md section 3),
                  receives HUD state frames.
  /ws/classifier  the iPhone YAMNet app. Receives every audio frame unchanged,
                  sends back {"t":"result","ts":<newest audio ts>,"inference_ms":n,
                  "top":[{"label":"Doorbell","score":0.82}, ...]}.
  /ws/pendant     the Android pendant. Receives say frames unchanged.
  GET /           status JSON.
"""

import argparse
import asyncio
import itertools
import json
import time
from collections import OrderedDict
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

import labels
from state import StateMachine, direction_from_tag

TICK_S = 0.1
MOCK_STATES = [
    {"state": "idle"},
    {"state": "cue", "label": "doorbell", "dir": "right", "ttl_ms": 4000, "level": 4},
    {"state": "speech", "label": "speech", "dir": "left", "ttl_ms": 0, "level": 2},
    {"state": "name", "label": "name", "dir": "left", "ttl_ms": 4000, "level": 4},
    {"state": "alarm", "label": "siren", "dir": "near", "ttl_ms": 0, "level": 4},
]


def log(*parts):
    print(time.strftime("%H:%M:%S"), *parts, flush=True)


class Peer:
    """One socket with its own send queue, so a slow receiver never stalls the
    glasses receive loop. When the queue is full the oldest frame is dropped."""

    def __init__(self, ws: WebSocket, maxsize: int = 32):
        self.ws = ws
        self.queue: asyncio.Queue[str] = asyncio.Queue(maxsize=maxsize)
        self.task = asyncio.create_task(self._pump())

    def send(self, text: str):
        if self.queue.full():
            self.queue.get_nowait()
        self.queue.put_nowait(text)

    async def _pump(self):
        try:
            while True:
                await self.ws.send_text(await self.queue.get())
        except Exception:
            pass

    def close(self):
        self.task.cancel()


class Hub:
    def __init__(self, mock: bool):
        self.mock = mock
        self.glasses: set[Peer] = set()
        self.classifiers: set[Peer] = set()
        self.pendants: set[Peer] = set()
        self.sm = StateMachine()
        self.frame = {"state": "idle"}
        self.speaker_role = "unknown"
        self.direction_tag = None
        self.direction_at = 0.0
        self.audio_frames = 0
        self.results = 0
        self.last_result = None
        # audio ts -> laptop receive time, to measure the classifier round trip
        self.recv_at: OrderedDict[int, float] = OrderedDict()
        # Tier 0 log: once a second, what direction/speakerRole the glasses sent
        self.tier0 = {"frames": 0, "dirs": set(), "roles": set(), "t0": time.time()}

    def broadcast_state(self, frame: dict):
        self.frame = frame
        text = json.dumps(frame)
        for p in self.glasses:
            p.send(text)
        log("STATE", text)

    def on_audio(self, raw: str, msg: dict):
        now = time.time()
        self.audio_frames += 1
        self.speaker_role = msg.get("speakerRole") or "unknown"
        if msg.get("direction") is not None:
            self.direction_tag = msg["direction"]
            self.direction_at = now
        ts = msg.get("ts")
        if ts is not None:
            self.recv_at[ts] = now
            while len(self.recv_at) > 200:
                self.recv_at.popitem(last=False)
        for p in self.classifiers:
            p.send(raw)

        t = self.tier0
        t["frames"] += 1
        t["dirs"].add(msg.get("direction"))
        t["roles"].add(self.speaker_role)
        if now - t["t0"] >= 1.0:
            log(f"TIER0 {t['frames']} frames/s direction={sorted(t['dirs'], key=str)} speakerRole={sorted(t['roles'])}")
            self.tier0 = {"frames": 0, "dirs": set(), "roles": set(), "t0": now}

    def on_result(self, msg: dict):
        now = time.time()
        self.results += 1
        top = msg.get("top", [])
        self.last_result = msg
        scores = labels.scores_by_label(top)
        self.sm.observe(scores, now, self.speaker_role)
        sent = self.recv_at.get(msg.get("ts"))
        rtt = f"{(now - sent) * 1000:4.0f}ms" if sent else "   ?  "
        top3 = "  ".join(f"{c.get('label')}:{c.get('score', 0):.2f}" for c in top[:3])
        mine = " ".join(f"{k}={v:.2f}" for k, v in scores.items())
        log(f"RESULT rtt={rtt} inf={msg.get('inference_ms', '?')}ms  {top3}  -> {mine or '-'}")

    def on_say(self, raw: str):
        log("SAY", raw, f"-> {len(self.pendants)} pendant(s)")
        for p in self.pendants:
            p.send(raw)

    def current_direction(self, now: float) -> str:
        if now - self.direction_at > 1.0:
            return "near"
        return direction_from_tag(self.direction_tag)

    async def tick_loop(self):
        while True:
            frame = self.sm.step(time.time(), self.current_direction(time.time()))
            if frame is not None:
                self.broadcast_state(frame)
            await asyncio.sleep(TICK_S)

    async def mock_loop(self):
        for frame in itertools.cycle(MOCK_STATES):
            self.broadcast_state(frame)
            await asyncio.sleep(5)


def make_app(hub: Hub) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(hub.mock_loop() if hub.mock else hub.tick_loop())
        yield
        task.cancel()

    app = FastAPI(lifespan=lifespan)
    # The Even WebView enforces CORS; the manifest whitelist does not get around it.
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @app.get("/")
    async def status():
        return {
            "mode": "mock" if hub.mock else "live",
            "glasses": len(hub.glasses),
            "classifiers": len(hub.classifiers),
            "pendants": len(hub.pendants),
            "audio_frames": hub.audio_frames,
            "results": hub.results,
            "state": hub.frame,
            "last_result": hub.last_result,
            "speaker_role": hub.speaker_role,
            "direction_tag": hub.direction_tag,
        }

    async def serve(ws: WebSocket, pool: set, name: str, on_text):
        await ws.accept()
        peer = Peer(ws)
        pool.add(peer)
        log(f"{name} connected {ws.client}  ({len(pool)} now)")
        if name == "glasses":
            peer.send(json.dumps(hub.frame))
        try:
            while True:
                raw = await ws.receive_text()
                try:
                    msg = json.loads(raw)
                except ValueError:
                    log(f"{name}: bad json {raw[:80]!r}")
                    continue
                on_text(raw, msg)
        except WebSocketDisconnect:
            pass
        finally:
            pool.discard(peer)
            peer.close()
            log(f"{name} disconnected ({len(pool)} left)")

    def from_glasses(raw, msg):
        t = msg.get("t")
        if t == "audio":
            hub.on_audio(raw, msg)
        elif t == "say":
            hub.on_say(raw)

    def from_classifier(raw, msg):
        if msg.get("t") == "result" and not hub.mock:
            hub.on_result(msg)

    @app.websocket("/ws/glasses")
    async def ws_glasses(ws: WebSocket):
        await serve(ws, hub.glasses, "glasses", from_glasses)

    @app.websocket("/ws/classifier")
    async def ws_classifier(ws: WebSocket):
        await serve(ws, hub.classifiers, "classifier", from_classifier)

    @app.websocket("/ws/pendant")
    async def ws_pendant(ws: WebSocket):
        await serve(ws, hub.pendants, "pendant", lambda raw, msg: None)

    return app


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true", help="cycle every HUD state every 5 s")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    hub = Hub(mock=args.mock)
    uvicorn.run(make_app(hub), host=args.host, port=args.port, log_level="warning", ws_max_size=4 * 1024 * 1024)


if __name__ == "__main__":
    main()
