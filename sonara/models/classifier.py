"""Few-shot personalised prototype classifier with open-set rejection.

Each enrolled take becomes a prototype (a (T, D) sequence). A query is scored against every
prototype; per-intent distance = mean of the k nearest prototypes of that intent. The query is
accepted only if the best distance is under the threshold AND clearly better than the runner-up.

Only features/embeddings are stored — never raw audio.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .dtw import dtw_distance


@dataclass
class Prediction:
    intent: str | None          # None = rejected
    best: str                   # best-scoring intent even if rejected
    distance: float
    margin: float               # runner-up distance − best distance
    threshold: float
    scores: dict[str, float]

    @property
    def accepted(self) -> bool:
        return self.intent is not None

    @property
    def score(self) -> float:
        """0..1 display score (1 = very close match). Not a calibrated probability."""
        return float(max(0.0, min(1.0, 1.0 - self.distance / (self.threshold * 1.5 + 1e-9))))

    def to_dict(self) -> dict:
        return {"intent": self.intent, "best": self.best, "distance": round(self.distance, 4),
                "margin": round(self.margin, 4), "threshold": round(self.threshold, 4),
                "score": round(self.score, 3),
                "scores": {k: round(v, 4) for k, v in self.scores.items()}}


class PrototypeClassifier:
    def __init__(self, backend: str, matcher: str = "dtw", k: int = 2):
        self.backend = backend
        self.matcher = matcher
        self.k = k
        self.labels: list[str] = []
        self.seqs: list[np.ndarray] = []
        self.threshold: float = 0.0

    # ---- enrollment -------------------------------------------------------------------------
    def add(self, label: str, seq: np.ndarray) -> None:
        self.labels.append(label)
        self.seqs.append(np.asarray(seq, dtype=np.float32))

    def remove_label(self, label: str) -> None:
        keep = [i for i, l in enumerate(self.labels) if l != label]
        self.labels = [self.labels[i] for i in keep]
        self.seqs = [self.seqs[i] for i in keep]

    @property
    def classes(self) -> list[str]:
        return sorted(set(self.labels))

    def counts(self) -> dict[str, int]:
        return {c: self.labels.count(c) for c in self.classes}

    # ---- scoring ----------------------------------------------------------------------------
    def _dist(self, a: np.ndarray, b: np.ndarray) -> float:
        if self.matcher == "mean":
            am, bm = a.mean(0), b.mean(0)
            return float(1 - am @ bm / (np.linalg.norm(am) * np.linalg.norm(bm) + 1e-9))
        metric = "cosine" if self.backend == "oww" else "euclidean"
        return dtw_distance(a, b, metric=metric)

    def scores(self, seq: np.ndarray, exclude: int | None = None) -> dict[str, float]:
        per: dict[str, list[float]] = {}
        for i, (lab, proto) in enumerate(zip(self.labels, self.seqs)):
            if i == exclude:
                continue
            per.setdefault(lab, []).append(self._dist(seq, proto))
        return {lab: float(np.mean(sorted(d)[: self.k])) for lab, d in per.items()}

    def predict(self, seq: np.ndarray, threshold: float | None = None,
                margin: float = 0.05) -> Prediction:
        if not self.seqs:
            raise RuntimeError("no enrolled prototypes — run scripts/enroll.py first")
        thr = threshold if threshold else self.threshold or float("inf")
        sc = self.scores(seq)
        ranked = sorted(sc.items(), key=lambda kv: kv[1])
        best, d = ranked[0]
        gap = ranked[1][1] - d if len(ranked) > 1 else float("inf")
        ok = d <= thr and gap >= margin
        return Prediction(best if ok else None, best, d, gap, thr, sc)

    def calibrate(self, slack: float = 1.25) -> float:
        """Leave-one-out: threshold = slack × 90th percentile of correct-class nearest distances."""
        own = []
        for i, lab in enumerate(self.labels):
            if self.labels.count(lab) < 2:
                continue
            sc = self.scores(self.seqs[i], exclude=i)
            own.append(sc[lab])
        self.threshold = float(np.percentile(own, 90) * slack) if own else 0.0
        return self.threshold

    # ---- persistence (features only, no audio) ----------------------------------------------
    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        lengths = np.array([len(s) for s in self.seqs])
        np.savez_compressed(path.with_suffix(".npz"), data=np.concatenate(self.seqs),
                            lengths=lengths, labels=np.array(self.labels))
        path.with_suffix(".json").write_text(json.dumps({
            "backend": self.backend, "matcher": self.matcher, "k": self.k,
            "threshold": self.threshold, "counts": self.counts()}, indent=2))

    @classmethod
    def load(cls, path: str | Path) -> "PrototypeClassifier":
        path = Path(path)
        meta = json.loads(path.with_suffix(".json").read_text())
        clf = cls(meta["backend"], meta.get("matcher", "dtw"), meta.get("k", 2))
        clf.threshold = meta.get("threshold", 0.0)
        z = np.load(path.with_suffix(".npz"), allow_pickle=False)
        offs = np.cumsum(np.r_[0, z["lengths"]])
        for lab, a, b in zip(z["labels"], offs[:-1], offs[1:]):
            clf.add(str(lab), z["data"][a:b])
        return clf
