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


def dtw_distances(a: np.ndarray, templates: list[np.ndarray],
                  band: float | None = .2, batch_size: int = 16) -> list[float]:
    """Exact DTW against bounded batches, sharing the Python row loop.

    Each template keeps its own band, path costs and lengths. Padding never enters
    an alignment. This uses the same recurrence/normalization as dtw_distance;
    it does not downsample features or approximate scores. Workspace is bounded
    by batch_size × 600 × 128 rather than the whole profile/query cost matrix.
    """
    if band is not None and not 0 <= band <= 1:
        raise ValueError("DTW band must be in [0, 1] or None")
    if not 1 <= batch_size <= 16 or len(templates) > 100:
        raise ValueError("DTW requires batches of 1–16 and at most 100 templates")
    result = [float("inf")] * len(templates)
    a = np.asarray(a, dtype=np.float64)
    if (a.ndim != 2 or not 1 <= len(a) <= 600 or not 1 <= a.shape[1] <= 128
            or not np.isfinite(a).all()):
        return result
    valid = []
    for index, template in enumerate(templates):
        template = np.asarray(template, dtype=np.float64)
        if (template.ndim == 2 and 1 <= len(template) <= 600
                and template.shape[1] == a.shape[1] and np.isfinite(template).all()):
            valid.append((index, template))
    if len(valid) == 1:
        index, template = valid[0]
        result[index] = dtw_distance(a, template, band=band)
        return result
    n, dimensions = a.shape
    for start in range(0, len(valid), batch_size):
        chunk = valid[start:start + batch_size]
        sizes = np.array([len(template) for _, template in chunk], dtype=np.int32)
        count, m = len(chunk), int(sizes.max())
        data = np.zeros((count, m, dimensions), dtype=np.float64)
        for k, (_, template) in enumerate(chunk):
            data[k, :len(template)] = template
        widths = (np.maximum(n, sizes) if band is None else np.maximum(
            np.abs(n - sizes), np.ceil(band * np.maximum(n, sizes)).astype(np.int32)))
        prev = np.full((count, m + 1), np.inf)
        prev[:, 0] = 0.
        row = np.full_like(prev, np.inf)
        lengths = np.zeros((count, m + 1), dtype=np.int32)
        next_lengths = np.zeros_like(lengths)
        indices = np.arange(m)
        for i in range(1, n + 1):
            left = np.maximum(1, i - widths)
            right = np.minimum(sizes, i + widths)
            lo, hi = int(left.min()), int(right.max())
            columns = indices[:hi - lo + 1]
            cells = columns + lo
            mask = (cells[None, :] >= left[:, None]) & (cells[None, :] <= right[:, None])
            difference = data[:, lo - 1:hi] - a[i - 1]
            costs = np.sqrt(np.einsum("bjd,bjd->bj", difference, difference, optimize=False) / dimensions)
            costs[~mask] = 0.
            diagonal, vertical = prev[:, lo - 1:hi], prev[:, lo:hi + 1]
            incoming_lengths = np.where(diagonal <= vertical, lengths[:, lo - 1:hi], lengths[:, lo:hi + 1])
            cumulative = np.cumsum(costs, axis=1)
            offsets = np.minimum(diagonal, vertical)
            offsets[:, 1:] -= cumulative[:, :-1]
            offsets[~mask] = np.inf
            minima = np.minimum.accumulate(offsets, axis=1)
            origins = np.maximum.accumulate(np.where(offsets <= minima, columns[None, :], 0), axis=1)
            row.fill(np.inf)
            values = cumulative + minima
            values[~mask] = np.inf
            row[:, lo:hi + 1] = values
            next_lengths.fill(0)
            path_lengths = np.take_along_axis(incoming_lengths, origins, axis=1) + columns[None, :] - origins + 1
            path_lengths[~mask] = 0
            next_lengths[:, lo:hi + 1] = path_lengths
            prev, row = row, prev
            lengths, next_lengths = next_lengths, lengths
        for k, (index, _) in enumerate(chunk):
            length = int(lengths[k, sizes[k]])
            if length:
                result[index] = float(max(0., prev[k, sizes[k]]) / length)
    return result
