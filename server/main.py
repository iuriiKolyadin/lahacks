"""Earshot hub: glasses <-> iPhone classifier.

    python main.py              # real: needs the plugin and a classifier on /ws/classifier
    python main.py --classify   # real, and runs YAMNet on this computer: no iPhone needed
    python main.py --mock       # cycles every HUD state every 5 s, no classifier
    python main.py --stt deepgram   # also caption other people's speech (captions.py)

Sockets (all on port 8000):
  /ws/glasses     the plugin. Sends audio and say frames (PLAN.md section 3)
                  and alert frames (docs/BRIDGE.md), receives HUD state frames;
                  a speech frame carries "text" (the captions) when --stt is on.
  /ws/classifier  the iPhone YAMNet app, or fake_classifier.py --model on this
                  computer (what --classify starts). Receives every audio frame unchanged,
                  sends back {"t":"result","ts":<newest audio ts>,"inference_ms":n,
                  "top":[{"label":"Doorbell","score":0.82}, ...]}.
  /ws/pendant     the Android companion. Receives say and alert frames unchanged.
  GET /           status JSON.
"""

import argparse
import asyncio
import itertools
import json
import os
import sys
import time
from collections import OrderedDict
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

import captions
import labels
import direction
from state import StateMachine

TICK_S = 0.1
# The plugin resends an active alert every 5 s. A pendant that connects within
# this long of the last one gets it replayed; anything older is stale.
ALERT_FRESH_S = 10
MOCK_STATES = [
    {"state": "idle"},
    {"state": "cue", "label": "doorbell", "dir": "right", "ttl_ms": 4000, "level": 4},
    {"state": "speech", "label": "speech", "dir": "left", "ttl_ms": 0, "level": 2,
     "text": "Hi, sorry to bother you. Is anyone sitting here, or can I take this seat?"},
    {"state": "name", "label": "name", "dir": "left", "ttl_ms": 4000, "level": 4},
    {"state": "alarm", "label": "siren", "dir": "near", "ttl_ms": 0, "level": 4},
]


def frame_rms(pcm_b64: str) -> float:
    """RMS of the sample-to-sample difference of one base64 int16 LE frame.

    Weights the direction estimate. The difference is a cheap high-pass, so the
    G2's loud sub-300 Hz rumble does not outweigh the alarm or knock being cued.
    """
    import array
    import base64

    try:
        a = array.array("h", base64.b64decode(pcm_b64))
    except ValueError:
        return 0.0
    if sys.byteorder != "little":
        a.byteswap()
    if len(a) < 2:
        return 0.0
    return (sum((a[i] - a[i - 1]) ** 2 for i in range(1, len(a))) / (len(a) - 1)) ** 0.5


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
    def __init__(self, mock: bool, dump=None, stt: str | None = None, whisper_model: str = "base.en"):
        self.mock = mock
        self.dump = dump  # open file: one JSON line per audio frame, for tools/dirtest.py
        self.glasses: set[Peer] = set()
        self.classifiers: set[Peer] = set()
        self.pendants: set[Peer] = set()
        self.sm = StateMachine()
        self.frame = {"state": "idle"}
        self.speaker_role = "unknown"
        self.direction_tag = None
        self.dir_tracker = direction.DirectionTracker()
        self.audio_frames = 0
        self.results = 0
        self.last_result = None
        self.alert = None  # newest alert frame from the plugin: {"raw", "msg", "at"}
        # audio ts -> laptop receive time, to measure the classifier round trip
        self.recv_at: OrderedDict[int, float] = OrderedDict()
        # Tier 0 log: once a second, what direction/speakerRole the glasses sent
        self.tier0 = {"frames": 0, "dirs": set(), "roles": set(), "t0": time.time()}
        self.captions = captions.create(stt, self.on_words, whisper_model) if stt and not mock else None

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
        tag = msg.get("direction")
        if tag is not None:
            self.direction_tag = tag
        rms = frame_rms(msg.get("pcm", ""))
        self.dir_tracker.add(tag, rms, now)
        if self.dump:
            self.dump.write(json.dumps({"t": round(now, 3), "direction": tag, "rms": round(rms), "role": self.speaker_role}) + "\n")
        ts = msg.get("ts")
        if ts is not None:
            self.recv_at[ts] = now
            while len(self.recv_at) > 200:
                self.recv_at.popitem(last=False)
        for p in self.classifiers:
            p.send(raw)
        if self.captions and msg.get("pcm"):
            import base64

            try:
                self.captions.feed(base64.b64decode(msg["pcm"]), self.speaker_role)
            except ValueError:
                pass

        t = self.tier0
        t["frames"] += 1
        t["dirs"].add(msg.get("direction"))
        t["roles"].add(self.speaker_role)
        if now - t["t0"] >= 1.0:
            ang = self.dir_tracker.angle(now)
            est = "none" if ang is None else f"{ang:+.0f} deg -> {direction.side_from_angle(ang)}"
            log(
                f"TIER0 {t['frames']} frames/s direction={sorted(t['dirs'], key=str)} "
                f"loud={est} speakerRole={sorted(t['roles'])}"
            )
            self.tier0 = {"frames": 0, "dirs": set(), "roles": set(), "t0": now}

    def on_result(self, msg: dict):
        now = time.time()
        self.results += 1
        top = msg.get("top", [])
        self.last_result = msg
        scores = labels.scores_by_label(top)
        self.sm.observe(scores, now, self.speaker_role, self.dir_tracker.side(now))
        sent = self.recv_at.get(msg.get("ts"))
        rtt = f"{(now - sent) * 1000:4.0f}ms" if sent else "   ?  "
        top3 = "  ".join(f"{c.get('label')}:{c.get('score', 0):.2f}" for c in top[:3])
        mine = " ".join(f"{k}={v:.2f}" for k, v in scores.items())
        log(f"RESULT rtt={rtt} inf={msg.get('inference_ms', '?')}ms  {top3}  -> {mine or '-'}")

    def on_say(self, raw: str):
        log("SAY", raw, f"-> {len(self.pendants)} pendant(s)")
        for p in self.pendants:
            p.send(raw)

    def on_alert(self, raw: str, msg: dict):
        """Relay an alert frame to the pendants. Logged only when it changes, not on every 5 s refresh."""
        prev = self.alert["msg"] if self.alert else {}
        self.alert = {"raw": raw, "msg": msg, "at": time.time()}
        if {k: v for k, v in msg.items() if k != "ts"} != {k: v for k, v in prev.items() if k != "ts"}:
            log("ALERT", raw, f"-> {len(self.pendants)} pendant(s)")
        for p in self.pendants:
            p.send(raw)

    def replay_alert(self, peer: Peer):
        """A pendant that connects while an alert is active rings straight away."""
        a = self.alert
        if a and a["msg"].get("active") and time.time() - a["at"] < ALERT_FRESH_S:
            peer.send(a["raw"])

    def on_words(self, now: float):
        self.sm.speech_heard(now, self.dir_tracker.side(now))

    async def tick_loop(self):
        while True:
            now = time.time()
            frame = self.sm.current(now)
            if self.captions and frame["state"] == "speech":
                text = self.captions.text(now)
                if text:
                    frame = {**frame, "text": text}
            if frame != self.frame:
                self.broadcast_state(frame)
            await asyncio.sleep(TICK_S)

    async def mock_loop(self):
        for frame in itertools.cycle(MOCK_STATES):
            self.broadcast_state(frame)
            await asyncio.sleep(5)


def make_app(hub: Hub) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        tasks = [asyncio.create_task(hub.mock_loop() if hub.mock else hub.tick_loop())]
        if hub.captions:
            tasks.append(asyncio.create_task(hub.captions.run()))
        yield
        for task in tasks:
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
            "direction_deg": hub.dir_tracker.angle(),
            "direction": hub.dir_tracker.side(),
            "alert": hub.alert["msg"] if hub.alert else None,
            "stt": type(hub.captions).__name__.lower() if hub.captions else None,
        }

    async def serve(ws: WebSocket, pool: set, name: str, on_text):
        await ws.accept()
        peer = Peer(ws)
        pool.add(peer)
        log(f"{name} connected {ws.client}  ({len(pool)} now)")
        if name == "glasses":
            peer.send(json.dumps(hub.frame))
        elif name == "pendant":
            hub.replay_alert(peer)
        try:
            while True:
                raw = await ws.receive_text()
                try:
                    msg = json.loads(raw)
                except ValueError:
                    log(f"{name}: bad json {raw[:80]!r}")
                    continue
                try:
                    on_text(raw, msg)
                except Exception as err:  # a bug handling one frame must not drop the socket
                    log(f"{name}: error handling frame: {err!r}")
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
        elif msg.get("type") == "alert":
            hub.on_alert(raw, msg)

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


def lan_urls(port: int) -> list[str]:
    """Base URLs other devices can try, best guess first.

    A phone hotspot on an IPv6-only carrier (T-Mobile) gives out no usable IPv4:
    a Mac shows 192.0.0.2, which is its own IPv4-over-IPv6 shim, not reachable
    from other devices. There the IPv6 address is the one to use.
    """
    import socket

    def outbound(family, target):  # the address used for outbound traffic; nothing is sent
        try:
            s = socket.socket(family, socket.SOCK_DGRAM)
            s.connect((target, 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except OSError:
            return None

    urls = []
    v6 = outbound(socket.AF_INET6, "2001:4860:4860::8888")
    if v6:
        urls.append(f"ws://[{v6}]:{port}")
    v4 = outbound(socket.AF_INET, "8.8.8.8")
    if v4 and not v4.startswith("192.0.0."):
        urls.append(f"ws://{v4}:{port}")
    return urls or [f"ws://<this laptop's IP>:{port}"]


def listen_sockets(port: int) -> list:
    """One IPv4 and one IPv6 listening socket on `port`, so both kinds of network work."""
    import socket

    socks = []
    for family, addr in ((socket.AF_INET, ("0.0.0.0", port)), (socket.AF_INET6, ("::", port))):
        try:
            s = socket.socket(family, socket.SOCK_STREAM)
            if os.name != "nt":  # on Windows SO_REUSEADDR lets two servers share a port
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if family == socket.AF_INET6:
                s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            s.bind(addr)
            socks.append(s)
        except OSError as err:
            log(f"could not listen on {addr[0]} port {port}: {err}")
    if not socks:
        raise SystemExit(f"port {port} is in use; stop the other server (fake_server.py?) first")
    return socks


def start_local_classifier(port: int, host: str | None):
    """Run YAMNet on this computer (fake_classifier.py --model) as a child process
    that connects back to /ws/classifier. Its results show up as RESULT lines here."""
    import atexit
    import subprocess

    try:
        import ai_edge_litert  # noqa: F401
        import numpy  # noqa: F401
    except ImportError:
        raise SystemExit("--classify needs the model packages: pip install -r requirements-model.txt")
    here = os.path.dirname(os.path.abspath(__file__))
    target = "127.0.0.1" if host in (None, "0.0.0.0") else ("::1" if host == "::" else host)
    if ":" in target:
        target = f"[{target}]"
    proc = subprocess.Popen(
        [sys.executable, os.path.join(here, "fake_classifier.py"), "--model", "--quiet",
         "--url", f"ws://{target}:{port}/ws/classifier"],
        cwd=here,
    )
    atexit.register(proc.terminate)
    log(f"classifier: YAMNet on this computer (pid {proc.pid}); no iPhone needed")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true", help="cycle every HUD state every 5 s")
    ap.add_argument("--classify", action="store_true",
                    help="run YAMNet on this computer instead of the iPhone app (needs requirements-model.txt)")
    ap.add_argument("--host", help="listen on this address only (default: all IPv4 and IPv6)")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--dump", help="append every audio frame's direction tag and rms to this .jsonl (read with tools/dirtest.py)")
    ap.add_argument("--stt", choices=["deepgram", "whisper"],
                    help="caption other people's speech: deepgram (DEEPGRAM_API_KEY) or whisper (requirements-stt.txt)")
    ap.add_argument("--whisper-model", default="base.en", help="with --stt whisper: tiny.en is faster, small.en is better")
    args = ap.parse_args()
    hub = Hub(mock=args.mock, dump=open(args.dump, "a", buffering=1) if args.dump else None,
              stt=args.stt, whisper_model=args.whisper_model)
    app = make_app(hub)
    opts = dict(log_level="warning", ws_max_size=4 * 1024 * 1024)
    if args.classify and not args.mock:
        start_local_classifier(args.port, args.host)  # retries until the server below is listening
    if args.host:
        uvicorn.run(app, host=args.host, port=args.port, **opts)
        return
    socks = listen_sockets(args.port)
    log(f"Earshot hub ({'mock' if args.mock else 'live'}) on port {args.port}. Point the devices at:")
    for base in lan_urls(args.port):
        log(f"  plugin {base}/ws/glasses    companion {base}/ws/pendant"
            + ("" if args.classify else f"    iPhone {base}/ws/classifier"))
    log("Nothing more prints until something connects.")
    uvicorn.Server(uvicorn.Config(app, **opts)).run(sockets=socks)


if __name__ == "__main__":
    main()
