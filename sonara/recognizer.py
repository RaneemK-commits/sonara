"""Validated audio → conservative trim → MFCC → personalized DTW → intent/UNKNOWN."""
from __future__ import annotations

import re
import threading
import time
import zipfile
from pathlib import Path

import numpy as np

from .audio.vad import trim_silence
from .config import Config
from .metrics import METRICS
from .models.classifier import Prediction, PrototypeClassifier
from .models.embedder import MFCCEmbedder
from .models.features import FeatureConfig


def profile_path(cfg: Config, profile_id: str | None = None) -> Path:
    profile_id = profile_id or cfg.section("recognition").get("profile_id", "patient_001")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", profile_id):
        raise ValueError("profile ID must contain only letters, digits, underscores or hyphens")
    return cfg.path(cfg.section("recognition").get("profile_dir", "data/profiles")) / profile_id


class Recognizer:
    def __init__(self, cfg: Config, backend: str | None = None):
        # Transitional calling compatibility for the device entry point; no model selection.
        if backend not in (None, "mfcc"):
            raise ValueError("only MFCC recognition is supported; remove the obsolete backend override")
        self.backend = "mfcc"
        self.cfg, self.sr = cfg, 16000
        if cfg.section("audio").get("sample_rate", 16000) != self.sr:
            raise ValueError("recognition requires 16 kHz audio")
        self._lock = threading.RLock()
        self.feature_config = FeatureConfig(**cfg.section("features"))
        self.embedder = MFCCEmbedder(self.feature_config)
        rec = cfg.section("recognition")
        self.threshold = rec.get("threshold")
        self.margin = rec.get("margin", .12)
        self.profile_id = profile_path(cfg).name
        self.clf = self.new_classifier()
        self._stamp = None
        self.profile_error = ""
        active = profile_path(cfg).parent / "active.txt"
        if active.exists():
            self.profile_id = profile_path(cfg, active.read_text().strip()).name
        self.reload()

    def new_classifier(self) -> PrototypeClassifier:
        return PrototypeClassifier(band=self.cfg.section("recognition").get("band", .2),
                                   feature_config=self.feature_config)

    @property
    def ready(self) -> bool:
        with self._lock:
            self.reload()
            return bool(self.clf.seqs)

    def reload(self, profile_id: str | None = None) -> None:
        with self._lock:
            target = profile_path(self.cfg, profile_id or self.profile_id)
            metadata = target / "metadata.json"
            if not metadata.exists():
                if profile_id is not None:
                    raise ValueError("profile is missing or incomplete")
                self.clf = self.new_classifier()
                self._stamp = None
                return
            archive = target / "templates.npz"
            if not archive.exists():
                self.clf = self.new_classifier()
                self.profile_error = "profile is missing templates.npz"
                if profile_id is not None:
                    raise ValueError(self.profile_error)
                return
            stamp = (target.name, metadata.stat().st_mtime_ns, metadata.stat().st_size,
                     archive.stat().st_mtime_ns, archive.stat().st_size)
            if profile_id is None and stamp == self._stamp:
                return
            try:
                clf = PrototypeClassifier.load(target)
                if any(self.cfg.intent(label) is None for label in clf.classes):
                    raise ValueError("profile contains intents missing from config/intents.toml")
            except (ValueError, KeyError, OSError, EOFError, zipfile.BadZipFile) as exc:
                self.profile_error = str(exc)
                if profile_id is not None:
                    raise ValueError(f"cannot load profile: {exc}") from exc
                # Fail closed if a selected profile becomes corrupt.
                self.clf = self.new_classifier()
                return
            self.clf, self.profile_id, self._stamp = clf, target.name, stamp
            self.feature_config = clf.feature_config
            self.embedder = MFCCEmbedder(self.feature_config)
            self.profile_error = ""
            if profile_id is not None:
                active = target.parent / "active.txt"
                tmp = active.with_suffix(".tmp")
                tmp.write_text(self.profile_id)
                tmp.replace(active)

    def prepare(self, audio: np.ndarray, manual: bool = False) -> tuple[np.ndarray, dict]:
        audio = np.asarray(audio, dtype=np.float32)
        if (audio.ndim != 1 or not .3*self.sr <= audio.size <= 5*self.sr
                or not np.isfinite(audio).all() or np.max(np.abs(audio), initial=0) > 1.001):
            raise ValueError("record 0.3–5 seconds of finite mono audio in [-1, 1]")
        clipped = float(np.mean(np.abs(audio) >= .999))
        if clipped > .05:
            raise ValueError("recording is clipped; reduce microphone gain and repeat")
        audio = audio - audio.mean()  # remove DC before energy checks
        rms = float(np.sqrt(np.mean(audio.astype(np.float64)**2)))
        if rms < self.cfg.section("audio").get("min_rms", .00003):
            raise ValueError("recording is silent or too quiet; move microphone closer")
        a = self.cfg.section("audio")
        speech = audio if manual else trim_silence(audio, self.sr, factor=a.get("trim_factor", 2.),
                                                   pad_ms=a.get("trim_pad_ms", 180))
        if speech.size < .15*self.sr:
            raise ValueError("too little speech; try manual recording boundaries")
        return speech, {"duration_s": round(audio.size/self.sr, 2), "speech_s": round(speech.size/self.sr, 2),
                        "rms": round(rms, 6), "clipped_fraction": clipped,
                        "feedback": "Quiet recording; test carefully" if rms < .002 else "Recording valid"}

    def embed(self, audio: np.ndarray, manual: bool = False) -> np.ndarray | None:
        try:
            with self._lock:
                speech, _ = self.prepare(audio, manual)
                return self.embedder(speech)
        except (ValueError, TypeError):
            return None

    def recognize(self, audio: np.ndarray, manual: bool = False) -> Prediction:
        t0 = time.perf_counter()
        with self._lock:
            self.reload()
            seq = self.embed(audio, manual)
            if seq is None:
                result = Prediction(None, None, float("inf"), 0., 0., {}, reason="invalid or silent recording")
            else:
                result = self.clf.predict(seq, self.threshold, self.margin)
        result.latency_ms = (time.perf_counter()-t0)*1000
        METRICS.incr("accepted" if result.accepted else "rejected")
        return result
