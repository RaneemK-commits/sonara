"""Microphone capture with a persistent input stream and VAD-delimited utterances.

Audio is kept only in a bounded in-memory queue; nothing is written to disk here.
"""
from __future__ import annotations

import queue
import time

import numpy as np

from .vad import StreamingVAD


class AudioCapture:
    def __init__(self, sr: int = 16000, block_ms: int = 30, device: str | int | None = None,
                 max_utterance_s: float = 5.0, silence_end_ms: int = 700,
                 speech_start_factor: float = 3.0, min_speech_ms: int = 200):
        import sounddevice as sd  # optional dependency, imported lazily

        self.sr = sr
        self.block = int(sr * block_ms / 1000)
        self.max_blocks = int(max_utterance_s * 1000 / block_ms)
        self.vad = StreamingVAD(sr, block_ms, speech_start_factor, silence_end_ms, min_speech_ms)
        self._q: queue.Queue[np.ndarray] = queue.Queue(maxsize=int(10_000 / block_ms))  # ≤10 s
        dev = None if device in ("", None) else device
        self._stream = sd.InputStream(samplerate=sr, channels=1, dtype="float32",
                                      blocksize=self.block, device=dev, callback=self._cb)
        self._stream.start()

    def _cb(self, indata, frames, t, status):  # audio thread
        try:
            self._q.put_nowait(indata[:, 0].copy())
        except queue.Full:  # drop oldest to stay bounded
            try:
                self._q.get_nowait()
            except queue.Empty:
                pass
            self._q.put_nowait(indata[:, 0].copy())

    def flush(self) -> None:
        while not self._q.empty():
            self._q.get_nowait()

    def record_utterance(self, wait_s: float) -> np.ndarray | None:
        """Wait up to `wait_s` for speech to start, then record until trailing silence.

        Returns float32 mono audio in [-1, 1] or None if no speech started.
        """
        self.vad.reset()
        preroll: list[np.ndarray] = []
        deadline = time.monotonic() + wait_s
        while True:
            timeout = deadline - time.monotonic()
            if timeout <= 0:
                return None
            try:
                blk = self._q.get(timeout=min(timeout, 0.1))
            except queue.Empty:
                continue
            preroll = (preroll + [blk])[-5:]  # keep ~150 ms before onset
            if self.vad.update(blk) == "start":
                break
        chunks = list(preroll)
        for _ in range(self.max_blocks):
            blk = self._q.get(timeout=2.0)
            chunks.append(blk)
            if self.vad.update(blk) == "end":
                break
        return np.concatenate(chunks).astype(np.float32)

    def close(self) -> None:
        self._stream.stop()
        self._stream.close()


def record_fixed(seconds: float, sr: int = 16000, device=None) -> np.ndarray:
    """Simple blocking fixed-length recording (used by enrollment)."""
    import sounddevice as sd

    audio = sd.rec(int(seconds * sr), samplerate=sr, channels=1, dtype="float32",
                   device=None if device in ("", None) else device)
    sd.wait()
    return audio[:, 0]
