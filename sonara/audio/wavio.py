"""Minimal 16-bit PCM WAV read/write with the standard library (no soundfile dependency)."""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np


def read_wav(path: str | Path, max_seconds: float | None = 5.) -> tuple[np.ndarray, int]:
    try:
        with wave.open(str(path), "rb") as wf:
            sr, ch, width, frames = wf.getframerate(), wf.getnchannels(), wf.getsampwidth(), wf.getnframes()
            if (width != 2 or not 1 <= ch <= 8 or not 8000 <= sr <= 192000 or frames <= 0
                    or (max_seconds is not None and frames > sr * max_seconds)):
                raise ValueError("expected 16-bit PCM WAV, 0–5 seconds, 8–192 kHz, 1–8 channels")
            data = wf.readframes(frames)
        if len(data) != frames * ch * width:
            raise ValueError("truncated WAV recording")
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"invalid PCM WAV: {path}") from exc
    audio = np.frombuffer(data, dtype="<i2").astype(np.float32).reshape(-1, ch).mean(axis=1) / 32768.
    return audio.astype(np.float32), sr


def write_wav(path: str | Path, audio: np.ndarray, sr: int) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def resample_linear(audio: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    audio = np.asarray(audio, dtype=np.float32)
    if (audio.ndim != 1 or not audio.size or not np.isfinite(audio).all()
            or sr_in <= 0 or sr_out <= 0 or audio.size > sr_in * 5):
        raise ValueError("invalid audio or sample rate")
    if sr_in == sr_out:
        return audio
    n_out = int(round(audio.size * sr_out / sr_in))
    x_old = np.linspace(0, 1, audio.size, endpoint=False)
    x_new = np.linspace(0, 1, n_out, endpoint=False)
    return np.interp(x_new, x_old, audio).astype(np.float32)
