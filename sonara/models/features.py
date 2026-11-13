"""Classical features in pure numpy: log-mel and MFCC (+ deltas, CMVN). Used by the baseline."""
from __future__ import annotations

from functools import lru_cache

import numpy as np


def _hz_to_mel(f):
    return 2595.0 * np.log10(1.0 + np.asarray(f) / 700.0)


def _mel_to_hz(m):
    return 700.0 * (10 ** (np.asarray(m) / 2595.0) - 1.0)


@lru_cache(maxsize=8)
def mel_filterbank(sr: int, n_fft: int, n_mels: int, fmin: float = 20.0,
                   fmax: float | None = None) -> np.ndarray:
    fmax = fmax or sr / 2
    mels = np.linspace(_hz_to_mel(fmin), _hz_to_mel(fmax), n_mels + 2)
    bins = np.floor((n_fft + 1) * _mel_to_hz(mels) / sr).astype(int)
    fb = np.zeros((n_mels, n_fft // 2 + 1), dtype=np.float32)
    for m in range(1, n_mels + 1):
        l, c, r = bins[m - 1], bins[m], bins[m + 1]
        if c > l:
            fb[m - 1, l:c] = (np.arange(l, c) - l) / (c - l)
        if r > c:
            fb[m - 1, c:r] = (r - np.arange(c, r)) / (r - c)
    return fb


@lru_cache(maxsize=4)
def _dct_matrix(n_in: int, n_out: int) -> np.ndarray:
    n = np.arange(n_in)
    k = np.arange(n_out)[:, None]
    m = np.cos(np.pi / n_in * (n + 0.5) * k) * np.sqrt(2.0 / n_in)
    m[0] /= np.sqrt(2.0)
    return m.astype(np.float32)


def log_mel(audio: np.ndarray, sr: int = 16000, n_fft: int = 512, win: int = 400,
            hop: int = 160, n_mels: int = 40) -> np.ndarray:
    """Return (T, n_mels) log-mel energies (25 ms window, 10 ms hop)."""
    audio = np.asarray(audio, dtype=np.float32)
    audio = np.append(audio[0], audio[1:] - 0.97 * audio[:-1]) if audio.size > 1 else audio
    if audio.size < win:
        audio = np.pad(audio, (0, win - audio.size))
    n_frames = 1 + (audio.size - win) // hop
    idx = np.arange(win)[None, :] + hop * np.arange(n_frames)[:, None]
    frames = audio[idx] * np.hamming(win).astype(np.float32)
    spec = np.abs(np.fft.rfft(frames, n=n_fft)) ** 2
    return np.log(spec @ mel_filterbank(sr, n_fft, n_mels).T + 1e-6)


def deltas(x: np.ndarray, width: int = 2) -> np.ndarray:
    pad = np.pad(x, ((width, width), (0, 0)), mode="edge")
    num = sum(k * (pad[width + k: width + k + len(x)] - pad[width - k: width - k + len(x)])
              for k in range(1, width + 1))
    return num / (2 * sum(k * k for k in range(1, width + 1)))


def mfcc(audio: np.ndarray, sr: int = 16000, n_mfcc: int = 13, with_deltas: bool = True) -> np.ndarray:
    """Return (T, D) MFCCs with per-utterance mean/variance normalisation."""
    lm = log_mel(audio, sr)
    c = lm @ _dct_matrix(lm.shape[1], n_mfcc).T
    feats = np.hstack([c, deltas(c), deltas(deltas(c))]) if with_deltas else c
    feats = (feats - feats.mean(0)) / (feats.std(0) + 1e-6)
    return feats.astype(np.float32)
