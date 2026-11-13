"""Dynamic time warping over feature/embedding sequences."""
from __future__ import annotations

import numpy as np


def cosine_cost(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    an = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-9)
    bn = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-9)
    return 1.0 - an @ bn.T


def euclidean_cost(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    d = (a * a).sum(1)[:, None] + (b * b).sum(1)[None, :] - 2 * a @ b.T
    return np.sqrt(np.maximum(d, 0)) / np.sqrt(a.shape[1])


def dtw_distance(a: np.ndarray, b: np.ndarray, metric: str = "cosine",
                 band: float | None = 0.4) -> float:
    """Length-normalised DTW distance between sequences a (n, d) and b (m, d).

    `band` is a Sakoe-Chiba constraint as a fraction of the longer length (None = unconstrained).
    """
    c = cosine_cost(a, b) if metric == "cosine" else euclidean_cost(a, b)
    n, m = c.shape
    w = max(abs(n - m), int(band * max(n, m))) if band else max(n, m)
    D = np.full((n + 1, m + 1), np.inf)
    D[0, 0] = 0.0
    for i in range(1, n + 1):
        j0 = max(1, int(i * m / n) - w)
        j1 = min(m, int(i * m / n) + w)
        prev = D[i - 1]
        row = D[i]
        for j in range(j0, j1 + 1):
            row[j] = c[i - 1, j - 1] + min(prev[j - 1], prev[j], row[j - 1])
    return float(D[n, m] / (n + m))
