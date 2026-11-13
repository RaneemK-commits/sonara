"""Energy-based voice activity detection.

Deliberately cheap: it runs continuously in always-on mode so the neural model only wakes up
when there is speech (the main energy-saving mechanism of the pipeline).
"""
from __future__ import annotations

import numpy as np


def rms(block: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(block, dtype=np.float64)) + 1e-12))


def trim_silence(audio: np.ndarray, sr: int, frame_ms: int = 20, factor: float = 3.0,
                 pad_ms: int = 100) -> np.ndarray:
    """Trim leading/trailing silence using a noise floor estimated from the quietest frames."""
    if audio.size == 0:
        return audio
    frame = max(1, int(sr * frame_ms / 1000))
    n = audio.size // frame
    if n < 3:
        return audio
    energies = np.sqrt(np.mean(audio[: n * frame].reshape(n, frame) ** 2, axis=1) + 1e-12)
    floor = np.percentile(energies, 10)
    voiced = np.where(energies > max(floor * factor, 1e-4))[0]
    if voiced.size == 0:
        return audio[:0]
    pad = int(pad_ms / frame_ms)
    start = max(0, voiced[0] - pad) * frame
    end = min(n, voiced[-1] + 1 + pad) * frame
    return audio[start:end]


class StreamingVAD:
    """Stateful speech start/end detector over fixed-size blocks.

    Feed blocks with `update(block)`; it returns "start", "end" or None. The noise floor adapts
    slowly while no speech is present.
    """

    def __init__(self, sr: int, block_ms: int, start_factor: float = 3.0,
                 silence_end_ms: int = 700, min_speech_ms: int = 200):
        self.block_ms = block_ms
        self.start_factor = start_factor
        self.end_blocks = max(1, silence_end_ms // block_ms)
        self.min_blocks = max(1, min_speech_ms // block_ms)
        self.noise_floor = 1e-3
        self.reset()

    def reset(self) -> None:
        self.in_speech = False
        self.speech_blocks = 0
        self.silent_blocks = 0

    def update(self, block: np.ndarray) -> str | None:
        e = rms(block)
        is_voiced = e > max(self.noise_floor * self.start_factor, 2e-3)
        if not self.in_speech:
            if is_voiced:
                self.speech_blocks += 1
                if self.speech_blocks >= 2:  # 2 consecutive voiced blocks to start
                    self.in_speech = True
                    self.silent_blocks = 0
                    return "start"
            else:
                self.speech_blocks = 0
                self.noise_floor = 0.95 * self.noise_floor + 0.05 * e
            return None
        # in speech
        self.speech_blocks += 1
        if is_voiced:
            self.silent_blocks = 0
        else:
            self.silent_blocks += 1
            if self.silent_blocks >= self.end_blocks and self.speech_blocks >= self.min_blocks:
                self.in_speech = False
                return "end"
        return None
