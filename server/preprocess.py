"""Clean up G2 mic audio before YAMNet. Mirrors GlassesAudioFilter in the iPhone app.

The G2 stream is dominated by rumble below 300 Hz, about 35 dB louder than
the 1 to 4 kHz band where alarms, sirens and doorbells live. Raw, YAMNet hears
Music/Throbbing/Hum. So: a high-pass filter (HPF_STAGES Butterworth biquads at
HPF_HZ), then per-window gain to TARGET_RMS, capped at MAX_GAIN so silence is
not blown up into noise.
"""

import math

import numpy as np

RATE = 16000
HPF_HZ = 600.0
HPF_STAGES = 2
TARGET_RMS = 0.05
MAX_GAIN = 10.0


def _coefs(fc: float, fs: int = RATE, q: float = 1 / math.sqrt(2)):
    w0 = 2 * math.pi * fc / fs
    alpha = math.sin(w0) / (2 * q)
    c = math.cos(w0)
    a0 = 1 + alpha
    return ((1 + c) / 2 / a0, -(1 + c) / a0, (1 + c) / 2 / a0, -2 * c / a0, (1 - alpha) / a0)


class HighPass:
    """Streaming high-pass. Keeps state across frames, so feed it every frame in order."""

    def __init__(self, fc: float = HPF_HZ, stages: int = HPF_STAGES):
        self.b0, self.b1, self.b2, self.a1, self.a2 = _coefs(fc)
        self.state = [[0.0, 0.0, 0.0, 0.0] for _ in range(stages)]

    def __call__(self, x: np.ndarray) -> np.ndarray:
        y = np.asarray(x, dtype=np.float64).copy()
        b0, b1, b2, a1, a2 = self.b0, self.b1, self.b2, self.a1, self.a2
        for st in self.state:
            x1, x2, y1, y2 = st
            out = np.empty_like(y)
            for i, v in enumerate(y):
                o = b0 * v + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
                x2, x1, y2, y1 = x1, v, y1, o
                out[i] = o
            st[:] = [x1, x2, y1, y2]
            y = out
        return y


def normalize(window: np.ndarray) -> np.ndarray:
    rms = math.sqrt(float(np.mean(window**2))) + 1e-9
    return np.clip(window * min(MAX_GAIN, TARGET_RMS / rms), -1.0, 1.0)
