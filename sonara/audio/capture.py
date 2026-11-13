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
                 max_utterance_s: float = 5.0, silence_end_ms: int = 1200,
                 speech_start_factor: float = 3.0, min_speech_ms: int = 200):
        if sr != 16000 or not 5 <= block_ms <= 100 or not .3 <= max_utterance_s <= 5:
            raise ValueError("capture requires 16 kHz, 5–100 ms blocks, and 0.3–5 second utterances")
        self.sr = sr
        self.block = int(sr * block_ms / 1000)
        self.max_blocks = int(max_utterance_s * 1000 / block_ms)
        self.vad = StreamingVAD(sr, block_ms, speech_start_factor, silence_end_ms, min_speech_ms)
        self._q: queue.Queue[np.ndarray] = queue.Queue(maxsize=int(10_000 / block_ms))  # ≤10 s
        dev = None if device in ("", None) else device
        if isinstance(dev, str) and dev.startswith("alsa:"):
            from .alsa import ALSAInputStream
            self._stream = ALSAInputStream(sr, self.block, dev[5:], self._cb)
        else:
            try:
                import sounddevice as sd  # optional, imported lazily
            except (ImportError, OSError):
                from .alsa import ALSAInputStream
                if dev is not None:
                    raise RuntimeError("PortAudio unavailable; select an explicit alsa: device name")
                self._stream = ALSAInputStream(sr, self.block, "default", self._cb)
            else:
                self._stream = sd.InputStream(samplerate=sr, channels=1, dtype="float32",
                                              blocksize=self.block, device=dev, callback=self._cb)
        try:
            self._stream.start()
        except Exception:
            self._stream.close()
            raise

    def _cb(self, indata, frames, t, status):  # audio thread
        try:
            self._q.put_nowait(indata[:, 0].copy())
        except queue.Full:  # drop oldest to stay bounded
            try:
                self._q.get_nowait()
            except queue.Empty:
                pass
            try:
                self._q.put_nowait(indata[:, 0].copy())
            except queue.Full:
                pass

    def flush(self) -> None:
        while True:
            try:
                self._q.get_nowait()
            except queue.Empty:
                break

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
        for _ in range(max(0, self.max_blocks - len(chunks))):
            try:
                blk = self._q.get(timeout=2.0)
            except queue.Empty:
                break
            chunks.append(blk)
            if self.vad.update(blk) == "end":
                break
        return np.concatenate(chunks).astype(np.float32)

    def record_manual(self, seconds: float = 3.) -> np.ndarray:
        """Fixed manual boundary on the same input stream; never opens a second mic."""
        if not .3 <= seconds <= 5:
            raise ValueError("manual duration must be 0.3–5 seconds")
        self.flush()
        chunks = []
        for _ in range(int(np.ceil(seconds * self.sr / self.block))):
            try:
                chunks.append(self._q.get(timeout=2.))
            except queue.Empty as exc:
                raise RuntimeError("microphone stopped delivering audio") from exc
        return np.concatenate(chunks)[:int(seconds*self.sr)].astype(np.float32)

    def close(self) -> None:
        self._stream.stop()
        self._stream.close()
