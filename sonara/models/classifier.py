"""Personal MFCC templates with explicit open-set rejection and versioned persistence."""
from __future__ import annotations

import hashlib
import json
import os
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import numpy as np

from .dtw import dtw_distance
from .features import FeatureConfig


@dataclass
class Prediction:
    intent: str | None
    best: str | None
    distance: float
    margin: float
    threshold: float
    scores: dict[str, float]
    latency_ms: float = 0.
    reason: str = ""

    @property
    def accepted(self) -> bool:
        return self.intent is not None

    @property
    def score(self) -> float:
        """Closeness for the existing display; never a probability."""
        return max(0., min(1., 1 - self.distance / (self.threshold * 1.5))) if self.threshold > 0 else 0.

    def to_dict(self) -> dict:
        finite = lambda v: round(float(v), 4) if np.isfinite(v) else None
        return {"intent": self.intent, "accepted": self.accepted, "best": self.best,
                "distance": finite(self.distance), "margin": finite(self.margin),
                "threshold": finite(self.threshold), "scores": {k: finite(v) for k, v in self.scores.items()},
                "latency_ms": round(self.latency_ms, 2), "reason": self.reason, "score": self.score}


RecognitionResult = Prediction


class PrototypeClassifier:
    def __init__(self, k: int = 2,
                 band: float | None = .2, feature_config: FeatureConfig | None = None):
        if not 1 <= k <= 10:
            raise ValueError("k must be 1–10")
        if band is not None and not 0 <= band <= 1:
            raise ValueError("invalid DTW band")
        self.k, self.band = k, band
        self.feature_config = feature_config or FeatureConfig()
        self.labels: list[str] = []
        self.seqs: list[np.ndarray] = []
        self.threshold = .8
        self.margin = .12
        self.per_intent_thresholds: dict[str, float] = {}
        self.calibration: dict = {"requires_more_recordings": True, "reason": "not calibrated"}
        self.profile_id = ""
        self.created_at = datetime.now(timezone.utc).isoformat()

    def _valid(self, seq: np.ndarray) -> bool:
        return (seq.ndim == 2 and 1 <= len(seq) <= 600
                and seq.shape[1] == self.feature_config.n_mfcc * 3 and np.isfinite(seq).all())

    def add(self, label: str, seq: np.ndarray) -> None:
        seq = np.asarray(seq, dtype=np.float32)
        if not label or not self._valid(seq):
            raise ValueError("invalid template")
        if len(self.seqs) >= 100 or self.labels.count(label) >= 10:
            raise ValueError("template limit reached (10 per intent, 100 total)")
        if any(lab == label and np.array_equal(seq, existing) for lab, existing in zip(self.labels, self.seqs)):
            raise ValueError("duplicate recording; capture a new pronunciation")
        self.labels.append(label)
        self.seqs.append(seq.copy())
        self.calibration = {"requires_more_recordings": True, "reason": "templates changed; recalibrate"}
        self.per_intent_thresholds.clear()

    def remove_label(self, label: str) -> None:
        keep = [i for i, value in enumerate(self.labels) if value != label]
        self.labels = [self.labels[i] for i in keep]
        self.seqs = [self.seqs[i] for i in keep]
        self.per_intent_thresholds.clear()
        self.calibration = {"requires_more_recordings": True, "reason": "templates changed; recalibrate"}

    @property
    def classes(self) -> list[str]:
        return sorted(set(self.labels))

    def counts(self) -> dict[str, int]:
        return {c: self.labels.count(c) for c in self.classes}

    def _dist(self, a: np.ndarray, b: np.ndarray) -> float:
        return dtw_distance(a, b, band=self.band)

    def scores(self, seq: np.ndarray, exclude: int | None = None) -> dict[str, float]:
        per: dict[str, list[float]] = {}
        for i, (label, template) in enumerate(zip(self.labels, self.seqs)):
            if i != exclude:
                per.setdefault(label, []).append(self._dist(seq, template))
        return {label: float(np.mean(sorted(values)[:self.k])) for label, values in per.items()}

    def predict(self, seq: np.ndarray, threshold: float | None = None,
                margin: float | None = None) -> Prediction:
        t0 = time.perf_counter()
        seq = np.asarray(seq, dtype=np.float32)
        thr = self.threshold if threshold is None else float(threshold)
        gap_required = self.margin if margin is None else float(margin)
        if not self.seqs or not self._valid(seq):
            return Prediction(None, None, float("inf"), 0., thr, {}, reason="invalid input or empty profile")
        sc = self.scores(seq)
        ranked = sorted(sc.items(), key=lambda item: item[1])
        best, distance = ranked[0]
        gap = ranked[1][1] - distance if len(ranked) > 1 else float("inf")
        thr = min(thr, self.per_intent_thresholds.get(best, thr))
        ok = (np.isfinite(thr) and thr > 0 and np.isfinite(distance) and distance <= thr
              and np.isfinite(gap_required) and gap_required >= 0 and gap >= gap_required)
        return Prediction(best if ok else None, best, distance, gap, thr, sc,
                          (time.perf_counter()-t0)*1000, "" if ok else "distant or ambiguous")

    def calibrate(self, slack: float = 1.15, unknown: list[np.ndarray] | None = None) -> float:
        """LOO positives capped by cross-intent/optional UNKNOWN negatives and fallback.

        Enrollment statistics are diagnostic, not a validated error-rate guarantee.
        No held-out evaluation recording belongs here.
        """
        positives = {c: [] for c in self.classes}
        negatives = {c: [] for c in self.classes}
        for i, label in enumerate(self.labels):
            for c, d in self.scores(self.seqs[i], exclude=i).items():
                (positives if c == label else negatives)[c].append(d)
        for seq in unknown or []:
            for c, d in self.scores(seq).items():
                negatives[c].append(d)
        detail = {}
        self.per_intent_thresholds = {}
        for c in self.classes:
            pos, neg = positives[c], negatives[c]
            p90 = float(np.percentile(pos, 90)) if pos else None
            n10 = float(np.percentile(neg, 10)) if neg else None
            limit = min(self.threshold, max(.05, p90 * slack) if p90 is not None else .6,
                        n10 * .8 if n10 is not None else .6)
            self.per_intent_thresholds[c] = max(0., limit)
            reliable = len(pos) >= 3 and len(neg) >= 3 and p90 < limit
            detail[c] = {"positive_loo": len(pos), "negative": len(neg), "positive_p90": p90,
                         "negative_p10": n10, "threshold": limit, "requires_more_recordings": not reliable}
        self.calibration = {"method": "leave-one-out positives and cross-intent negatives",
                            "requires_more_recordings": not detail or any(
                                d["requires_more_recordings"] for d in detail.values()),
                            "intents": detail, "warning": "Enrollment calibration does not guarantee UNKNOWN rejection."}
        return self.threshold

    def save(self, path: str | Path) -> None:
        """Commit metadata last; checksum rejects interrupted or mixed-generation saves."""
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        generation = uuid4().hex
        tmp = path / f".{generation}.npz"
        data = np.concatenate(self.seqs) if self.seqs else np.empty((0, self.feature_config.n_mfcc*3), np.float32)
        np.savez_compressed(tmp, data=data, lengths=np.array([len(s) for s in self.seqs], dtype=np.int32),
                            labels=np.array(self.labels, dtype=str))
        meta = {"version": 1, "profile_id": self.profile_id or path.name, "created_at": self.created_at,
                "updated_at": datetime.now(timezone.utc).isoformat(), "feature_config": self.feature_config.to_dict(),
                "matching": {"k": self.k, "band": self.band, "margin": self.margin},
                "threshold": self.threshold, "per_intent_thresholds": self.per_intent_thresholds,
                "counts": self.counts(), "calibration": self.calibration,
                "templates_sha256": hashlib.sha256(tmp.read_bytes()).hexdigest()}
        meta_tmp = path / f".{generation}.json"
        meta_tmp.write_text(json.dumps(meta, indent=2, allow_nan=False))
        os.replace(tmp, path / "templates.npz")
        os.replace(meta_tmp, path / "metadata.json")

    @classmethod
    def load(cls, path: str | Path) -> PrototypeClassifier:
        path = Path(path)
        meta = json.loads((path / "metadata.json").read_text())
        if meta["version"] != 1:
            raise ValueError("unsupported profile version; re-enroll")
        archive = path / "templates.npz"
        if archive.stat().st_size > 16_000_000:
            raise ValueError("profile too large")
        if hashlib.sha256(archive.read_bytes()).hexdigest() != meta["templates_sha256"]:
            raise ValueError("incomplete profile; template checksum mismatch")
        with zipfile.ZipFile(archive) as z:
            if sum(i.file_size for i in z.infolist()) > 16_000_000:
                raise ValueError("profile expands beyond size limit")
        matching = meta["matching"]
        clf = cls(k=matching["k"], band=matching["band"], feature_config=FeatureConfig(**meta["feature_config"]))
        with np.load(archive, allow_pickle=False) as z:
            lengths, labels, data = z["lengths"], z["labels"], z["data"]
            if (lengths.ndim != 1 or labels.ndim != 1 or len(labels) != len(lengths)
                    or len(labels) > 100 or not np.issubdtype(lengths.dtype, np.integer)
                    or np.any(lengths < 1) or np.any(lengths > 600) or lengths.sum() != len(data)):
                raise ValueError("invalid profile arrays")
            offsets = np.cumsum(np.r_[0, lengths])
            for label, a, b in zip(labels, offsets[:-1], offsets[1:]):
                clf.add(str(label), data[a:b])
        clf.threshold = float(meta["threshold"])
        clf.margin = float(matching["margin"])
        clf.per_intent_thresholds = {c: float(v) for c, v in meta["per_intent_thresholds"].items()}
        if (not np.isfinite(clf.threshold) or clf.threshold < 0 or not np.isfinite(clf.margin)
                or clf.margin < 0 or any(not np.isfinite(v) or v < 0 for v in clf.per_intent_thresholds.values())):
            raise ValueError("invalid profile thresholds")
        clf.calibration = meta["calibration"]
        clf.profile_id, clf.created_at = meta["profile_id"], meta["created_at"]
        return clf
