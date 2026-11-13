"""Audio → sequence-of-vectors front-ends.

* `OWWEmbedder`  — neural: openWakeWord melspectrogram ONNX + Google speech-embedding CNN
                    (pretrained on large speech corpora; frozen). 96-d vector every 80 ms.
* `MFCCEmbedder` — classical baseline: 39-d MFCC+Δ+ΔΔ every 10 ms.

Both return float32 arrays of shape (T, D).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .features import mfcc


class MFCCEmbedder:
    name = "mfcc"

    def __init__(self, sr: int = 16000):
        self.sr = sr

    def __call__(self, audio: np.ndarray) -> np.ndarray:
        return mfcc(audio, self.sr)


class OWWEmbedder:
    """Frozen pretrained speech-embedding network (via openWakeWord's ONNX exports).

    melspectrogram.onnx : (1, n_samples) int16-scaled float32 → (1, 1, frames, 32)
    embedding_model.onnx: (N, 76, 32, 1) → (N, 1, 1, 96); 76 mel frames ≈ 775 ms window,
                          we slide it by 8 frames (80 ms).
    """

    name = "oww"
    WINDOW = 76
    STEP = 8

    def __init__(self, melspec_path: str | Path, embedding_path: str | Path, threads: int = 2):
        import onnxruntime as ort

        for p in (melspec_path, embedding_path):
            if not Path(p).exists():
                raise FileNotFoundError(f"{p} missing — run `python scripts/download_models.py`")
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = threads  # leave cores free for server/TTS on the UNO Q
        prov = ["CPUExecutionProvider"]
        self.mel = ort.InferenceSession(str(melspec_path), opts, providers=prov)
        self.emb = ort.InferenceSession(str(embedding_path), opts, providers=prov)
        self._mel_in = self.mel.get_inputs()[0].name
        self._emb_in = self.emb.get_inputs()[0].name

    def melspec(self, audio: np.ndarray) -> np.ndarray:
        x = (np.asarray(audio, dtype=np.float32) * 32767.0)[None, :]
        out = self.mel.run(None, {self._mel_in: x})[0]
        return np.squeeze(out).reshape(-1, 32) / 10.0 + 2.0  # openWakeWord's transform

    def __call__(self, audio: np.ndarray) -> np.ndarray:
        audio = np.asarray(audio, dtype=np.float32)
        min_len = 16000  # ≥1 s so at least one 76-frame window exists; centre-pad short clips
        if audio.size < min_len:
            pad = min_len - audio.size
            audio = np.pad(audio, (pad // 2, pad - pad // 2))
        mel = self.melspec(audio)
        starts = range(0, mel.shape[0] - self.WINDOW + 1, self.STEP)
        batch = np.stack([mel[s:s + self.WINDOW] for s in starts])[..., None].astype(np.float32)
        emb = self.emb.run(None, {self._emb_in: batch})[0]
        return emb.reshape(len(batch), -1).astype(np.float32)


def make_embedder(backend: str, cfg=None):
    if backend == "mfcc":
        return MFCCEmbedder()
    if backend == "oww":
        rec = cfg.section("recognition") if cfg else {}
        root = cfg.path if cfg else Path
        return OWWEmbedder(root(rec.get("oww_melspec_model", "models/melspectrogram.onnx")),
                           root(rec.get("oww_embedding_model", "models/embedding_model.onnx")))
    raise ValueError(f"unknown backend {backend!r}")
