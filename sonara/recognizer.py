"""Glue: audio → VAD trim → embedder → prototype classifier → Prediction."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .audio.vad import trim_silence
from .config import Config
from .metrics import METRICS
from .models.classifier import Prediction, PrototypeClassifier
from .models.embedder import make_embedder


def profile_path(cfg: Config, backend: str, bed_id: str | None = None) -> Path:
    rec = cfg.section("recognition")
    return cfg.path(rec.get("profile_dir", "data/profiles")) / f"{bed_id or cfg.bed_id}_{backend}"


class Recognizer:
    def __init__(self, cfg: Config, backend: str | None = None):
        rec = cfg.section("recognition")
        self.cfg = cfg
        self.sr = cfg.section("audio").get("sample_rate", 16000)
        self.backend = backend or rec.get("backend", "oww")
        self.embedder = make_embedder(self.backend, cfg)
        self.threshold = rec.get("threshold", 0.0) or None
        self.margin = rec.get("margin", 0.05)
        path = profile_path(cfg, self.backend)
        if path.with_suffix(".json").exists():
            self.clf = PrototypeClassifier.load(path)
        else:
            self.clf = PrototypeClassifier(self.backend, rec.get("matcher", "dtw"))

    @property
    def ready(self) -> bool:
        return bool(self.clf.seqs)

    def embed(self, audio: np.ndarray) -> np.ndarray | None:
        with METRICS.time("vad_trim"):
            speech = trim_silence(audio, self.sr)
        if speech.size < self.sr * 0.15:
            return None
        with METRICS.time("embed"):
            return self.embedder(speech)

    def recognize(self, audio: np.ndarray) -> Prediction | None:
        seq = self.embed(audio)
        if seq is None:
            return None
        with METRICS.time("classify"):
            pred = self.clf.predict(seq, self.threshold, self.margin)
        METRICS.incr("accepted" if pred.accepted else "rejected")
        return pred
