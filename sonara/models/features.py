"""MFCC + delta + acceleration features; no learned weights or inference runtime."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache

import numpy as np


@dataclass(frozen=True)
class FeatureConfig:
    sample_rate: int = 16000
    window_length_ms: float = 25
    hop_length_ms: float = 10
    n_fft: int = 512
    n_mels: int = 40
    n_mfcc: int = 13
    pre_emphasis: float = 0.97
    normalization: str = "cmvn"
    variance_floor: float = 0.01

    def __post_init__(self) -> None:
        win = int(self.sample_rate * self.window_length_ms / 1000)
        hop = int(self.sample_rate * self.hop_length_ms / 1000)
        if (self.sample_rate != 16000 or not 1 <= hop <= win <= self.n_fft <= 4096
                or not 1 <= self.n_mfcc <= self.n_mels <= 128
                or not 0 <= self.pre_emphasis <= 1 or self.variance_floor <= 0
                or self.normalization not in ("cmvn", "mean", "none")):
            raise ValueError("invalid MFCC configuration (16 kHz required)")

    def to_dict(self) -> dict:
        return asdict(self)


@lru_cache(maxsize=8)
def mel_filterbank(sr: int, n_fft: int, n_mels: int, fmin: float = 20.,
                   fmax: float | None = None) -> np.ndarray:
    fmax = sr / 2 if fmax is None else fmax
    mel = lambda f: 2595 * np.log10(1 + np.asarray(f) / 700)
    points = 700 * (10 ** (np.linspace(mel(fmin), mel(fmax), n_mels + 2) / 2595) - 1)
    freqs = np.fft.rfftfreq(n_fft, 1 / sr)
    left, center, right = points[:-2, None], points[1:-1, None], points[2:, None]
    return np.maximum(0, np.minimum((freqs - left) / (center - left),
                                    (right - freqs) / (right - center))).astype(np.float32)


@lru_cache(maxsize=8)
def _dct_matrix(n_in: int, n_out: int) -> np.ndarray:
    matrix = np.cos(np.pi / n_in * (np.arange(n_in) + .5) * np.arange(n_out)[:, None])
    matrix *= np.sqrt(2 / n_in)
    matrix[0] /= np.sqrt(2)
    return matrix.astype(np.float32)


def log_mel(audio: np.ndarray, sr: int = 16000, n_fft: int = 512, win: int = 400,
            hop: int = 160, n_mels: int = 40, pre_emphasis: float = .97) -> np.ndarray:
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim != 1 or not 0 < audio.size <= sr * 5 or not np.isfinite(audio).all():
        raise ValueError("expected finite mono audio, 1 sample to 5 seconds")
    if not 1 <= hop <= win <= n_fft:
        raise ValueError("invalid frame configuration")
    audio = audio.copy()
    audio[1:] -= pre_emphasis * audio[:-1].copy()
    # Include the partial last frame, including very short utterances.
    frames = max(1, 1 + int(np.ceil((audio.size - win) / hop)))
    audio = np.pad(audio, (0, (frames - 1) * hop + win - audio.size))
    windows = np.lib.stride_tricks.sliding_window_view(audio, win)[::hop]
    spectrum = np.abs(np.fft.rfft(windows * np.hamming(win), n=n_fft)) ** 2 / n_fft
    # einsum avoids spawning a BLAS thread team for these small matrices.
    energies = np.einsum("tf,mf->tm", spectrum, mel_filterbank(sr, n_fft, n_mels), optimize=False)
    return np.log(np.maximum(energies, 1e-12)).astype(np.float32)


def deltas(x: np.ndarray, width: int = 2) -> np.ndarray:
    pad = np.pad(x, ((width, width), (0, 0)), mode="edge")
    return sum(k * (pad[width+k:width+k+len(x)] - pad[width-k:width-k+len(x)])
               for k in range(1, width+1)) / (2 * sum(k*k for k in range(1, width+1)))


def mfcc(audio: np.ndarray, sr: int = 16000, n_mfcc: int = 13, with_deltas: bool = True,
         config: FeatureConfig | None = None) -> np.ndarray:
    cfg = config or FeatureConfig(sample_rate=sr, n_mfcc=n_mfcc)
    lm = log_mel(audio, cfg.sample_rate, cfg.n_fft,
                 int(cfg.sample_rate * cfg.window_length_ms / 1000),
                 int(cfg.sample_rate * cfg.hop_length_ms / 1000), cfg.n_mels, cfg.pre_emphasis)
    c = np.einsum("tm,dm->td", lm, _dct_matrix(cfg.n_mels, cfg.n_mfcc), optimize=False)
    feats = np.hstack((c, deltas(c), deltas(deltas(c)))) if with_deltas else c
    if cfg.normalization != "none":
        feats = feats - feats.mean(0)
        if cfg.normalization == "cmvn":
            feats /= np.maximum(feats.std(0), cfg.variance_floor)
    return feats.astype(np.float32)
