"""Path-length normalized DTW with a Sakoe–Chiba band and O(M) workspace."""
from __future__ import annotations
import numpy as np


def euclidean_cost(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.sqrt(np.mean((a[:, None, :] - b[None, :, :]) ** 2, axis=2))


def dtw_distance(a: np.ndarray, b: np.ndarray, metric: str = "euclidean",
                 band: float | None = .2) -> float:
    """Minimum accumulated RMS Euclidean cost / selected alignment path length.

    Band is a fraction of the longer sequence, widened only enough to reach both
    endpoints. Zero means diagonal-only for equal lengths; None is unconstrained.
    Ties prefer diagonal, then vertical, then horizontal, deterministically.
    Inputs are bounded to 600 frames × 128 features (5 s MFCC uses <=499 × 39).
    """
    if metric != "euclidean" or (band is not None and not 0 <= band <= 1):
        raise ValueError("DTW requires Euclidean metric and band in [0, 1] or None")
    a, b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    if (a.ndim != 2 or b.ndim != 2 or a.shape[1] != b.shape[1] or not a.size or not b.size
            or max(len(a), len(b)) > 600 or not 1 <= a.shape[1] <= 128
            or not np.isfinite(a).all() or not np.isfinite(b).all()):
        return float("inf")
    n, m = len(a), len(b)
    width = max(n, m) if band is None else max(abs(n-m), int(np.ceil(band * max(n, m))))
    prev = np.full(m+1, np.inf)
    prev[0] = 0
    lengths = np.zeros(m+1, dtype=np.int32)
    row = np.full(m+1, np.inf)
    next_lengths = np.zeros(m+1, dtype=np.int32)
    indices = np.arange(m+1)
    for i in range(1, n+1):
        lo, hi = max(1, i-width), min(m, i+width)
        difference = b[lo-1:hi] - a[i-1]
        c = np.sqrt(np.einsum("ij,ij->i", difference, difference, optimize=False) / a.shape[1])
        diagonal, vertical = prev[lo-1:hi], prev[lo:hi+1]
        base = np.minimum(diagonal, vertical)
        incoming_lengths = np.where(diagonal <= vertical, lengths[lo-1:hi], lengths[lo:hi+1])
        cumulative = np.cumsum(c)
        offsets = base.copy()
        offsets[1:] -= cumulative[:-1]
        minima = np.minimum.accumulate(offsets)
        # Latest equal minimum reproduces diagonal/vertical preference over horizontal.
        origins = np.maximum.accumulate(np.where(offsets <= minima, indices[:len(c)], 0))
        row.fill(np.inf)
        row[lo:hi+1] = cumulative + minima
        next_lengths.fill(0)
        next_lengths[lo:hi+1] = incoming_lengths[origins] + indices[:len(c)] - origins + 1
        prev, row = row, prev
        lengths, next_lengths = next_lengths, lengths
    return float(max(0., prev[m]) / lengths[m]) if lengths[m] else float("inf")
