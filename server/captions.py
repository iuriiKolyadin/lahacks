"""Live captions of other people's speech, for the HUD's speech state.

    python main.py --stt deepgram     # DEEPGRAM_API_KEY in the environment; ~0.5 s behind
    python main.py --stt whisper      # faster-whisper on this computer, offline; ~1-2 s behind

The hub feeds every glasses audio frame to feed(). Frames the glasses mark as
the wearer's own voice (speakerRole "self") are fed as silence, so the
wearer's words are never captioned but the stream's timing stays intact.
Whenever new words arrive, on_words(now) is called; the hub treats that as
speech heard, so captions come up without waiting for YAMNet's speech label.

text(now) is what the HUD shows: the newest MAX_CHARS of what was said,
final words then the in-progress guess. It empties CLEAR_S after the last new
word, so the next conversation does not open with the end of the last one.

The firmware font is only known to draw ASCII (hud.ts), so text is folded to ASCII.
"""

import asyncio
import json
import os
import time
import unicodedata
from typing import Callable

RATE = 16000
MAX_CHARS = 300
CLEAR_S = 8.0


def tail(s: str) -> str:
    """The last MAX_CHARS of s, starting on a whole word."""
    if len(s) <= MAX_CHARS:
        return s
    s = s[-MAX_CHARS:]
    return s[s.find(" ") + 1:] if " " in s else s


def log(*parts):
    print(time.strftime("%H:%M:%S"), "STT", *parts, flush=True)


def to_ascii(s: str) -> str:
    s = s.translate(str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"',
                                   "–": "-", "—": "-", "…": "..."}))
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


class Captions:
    """The text both backends produce, and the speech-heard callback."""

    def __init__(self, on_words: Callable[[float], None]):
        self.on_words = on_words
        self.final = ""
        self.interim = ""
        self.updated_at = float("-inf")

    def _changed(self, final: str, interim: str):
        final, interim = " ".join(to_ascii(final).split()), " ".join(to_ascii(interim).split())
        if not final and not interim:
            return
        now = time.time()
        if now - self.updated_at > CLEAR_S:
            self.final = ""
        if final:
            self.final = tail(f"{self.final} {final}".strip())
        self.interim = interim
        self.updated_at = now
        self.on_words(now)

    def text(self, now: float) -> str:
        if now - self.updated_at > CLEAR_S:
            return ""
        return tail(f"{self.final} {self.interim}".strip())

    def feed(self, pcm: bytes, speaker_role: str):
        raise NotImplementedError

    async def run(self):
        raise NotImplementedError


class Deepgram(Captions):
    """Streams the audio to Deepgram's live API; interim results update as people talk."""

    URL = ("wss://api.deepgram.com/v1/listen?model=nova-3&language=en&encoding=linear16"
           f"&sample_rate={RATE}&channels=1&interim_results=true&smart_format=true&endpointing=300")

    def __init__(self, on_words, key: str):
        super().__init__(on_words)
        self.key = key
        self.queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100)  # ~10 s of 100 ms frames

    def feed(self, pcm: bytes, speaker_role: str):
        if speaker_role == "self":
            pcm = bytes(len(pcm))
        if self.queue.full():
            self.queue.get_nowait()  # a stale second of audio is worse than a lost one
        self.queue.put_nowait(pcm)

    async def run(self):
        import websockets

        while True:
            first = await self.queue.get()  # connect only once the glasses are sending
            try:
                async with websockets.connect(self.URL, additional_headers={"Authorization": f"Token {self.key}"}) as ws:
                    log("connected to Deepgram")
                    await ws.send(first)
                    reader = asyncio.create_task(self._read(ws))
                    try:
                        while not reader.done():
                            try:
                                await ws.send(await asyncio.wait_for(self.queue.get(), 5))
                            except asyncio.TimeoutError:
                                # no audio (glasses gone); Deepgram closes after 10 s without this
                                await ws.send(json.dumps({"type": "KeepAlive"}))
                        reader.result()
                    finally:
                        reader.cancel()
            except asyncio.CancelledError:
                raise
            except Exception as err:
                status = getattr(getattr(err, "response", None), "status_code", None)
                if status in (401, 403):
                    log("Deepgram rejected DEEPGRAM_API_KEY; retrying in 30 s")
                    await asyncio.sleep(30)
                else:
                    log(f"Deepgram connection failed: {status or repr(err)}; retrying in 2 s")
                    await asyncio.sleep(2)

    async def _read(self, ws):
        async for raw in ws:
            msg = json.loads(raw)
            if msg.get("type") != "Results":
                continue
            alts = msg.get("channel", {}).get("alternatives") or [{}]
            words = alts[0].get("transcript", "")
            if msg.get("is_final"):
                self._changed(words, "")
            else:
                self._changed("", words)


class Whisper(Captions):
    """Runs faster-whisper on this computer every STEP_S over the current utterance.

    The utterance is the audio since the last committed words. A transcription
    whose last word ended more than END_GAP_S before the end of the audio means
    the speaker paused: its words are final and the buffer starts over. A long
    unbroken utterance commits all but its last segment, so each pass stays short;
    the buffer is cut in the gap before that segment, never inside a word, or the
    next pass would hear the cut-off word again.
    """

    STEP_S = 1.0
    END_GAP_S = 0.6
    LONG_S = 10.0
    MAX_S = 15.0

    def __init__(self, on_words, model: str):
        super().__init__(on_words)
        self.model_name = model
        self.buf = bytearray()

    def feed(self, pcm: bytes, speaker_role: str):
        self.buf += bytes(len(pcm)) if speaker_role == "self" else pcm
        over = len(self.buf) - int(self.MAX_S * RATE) * 2
        if over > 0:
            del self.buf[:over]

    def _load(self):
        from faster_whisper import WhisperModel

        try:
            import ctranslate2
            cuda = ctranslate2.get_cuda_device_count() > 0
        except Exception:
            cuda = False
        log(f"loading whisper {self.model_name} on {'GPU' if cuda else 'CPU'} (the first run downloads it)")
        return WhisperModel(self.model_name, device="cuda" if cuda else "cpu",
                            compute_type="float16" if cuda else "int8")

    async def run(self):
        import numpy as np

        model = await asyncio.to_thread(self._load)
        log("whisper ready")

        def transcribe(audio):
            segs, _ = model.transcribe(audio, language="en", beam_size=1, vad_filter=True,
                                       condition_on_previous_text=False)
            return [(s.start, s.end, s.text) for s in segs]

        while True:
            await asyncio.sleep(self.STEP_S)
            if len(self.buf) < RATE:  # under 0.5 s
                continue
            snap = bytes(self.buf)
            audio = np.frombuffer(snap, dtype=np.int16).astype(np.float32) / 32768
            dur = len(audio) / RATE
            try:
                segs = await asyncio.to_thread(transcribe, audio)
            except Exception as err:
                log(f"whisper failed: {err!r}")
                continue
            if not segs:
                if dur > 2:
                    del self.buf[:len(snap)]  # nothing but noise; frames that came in meanwhile stay
                self.interim = ""
                continue
            texts = [t for _, _, t in segs]
            if dur - segs[-1][1] > self.END_GAP_S:
                del self.buf[:len(snap)]
                self._changed(" ".join(texts), "")
            elif dur > self.LONG_S and len(segs) > 1:
                cut = (segs[-2][1] + segs[-1][0]) / 2
                del self.buf[:int(cut * RATE) * 2]
                self._changed(" ".join(texts[:-1]), texts[-1])
            else:
                self._changed("", " ".join(texts))


def create(kind: str, on_words: Callable[[float], None], whisper_model: str = "base.en") -> Captions:
    if kind == "deepgram":
        key = os.environ.get("DEEPGRAM_API_KEY")
        if not key:
            raise SystemExit("--stt deepgram needs DEEPGRAM_API_KEY set (console.deepgram.com)")
        return Deepgram(on_words, key)
    if kind == "whisper":
        try:
            import faster_whisper  # noqa: F401
            import numpy  # noqa: F401
        except ImportError:
            raise SystemExit("--stt whisper needs: pip install -r requirements-stt.txt")
        return Whisper(on_words, whisper_model)
    raise ValueError(kind)
