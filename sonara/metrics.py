"""Per-stage latency tracking (kept in memory; exposed at /api/metrics)."""
from __future__ import annotations

import statistics
import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager


class Metrics:
    def __init__(self, keep: int = 200):
        self._lock = threading.Lock()
        self._stages: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=keep))
        self.counters: dict[str, int] = defaultdict(int)

    @contextmanager
    def time(self, stage: str):
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.record(stage, (time.perf_counter() - t0) * 1000)

    def record(self, stage: str, ms: float) -> None:
        with self._lock:
            self._stages[stage].append(ms)

    def incr(self, name: str) -> None:
        with self._lock:
            self.counters[name] += 1

    def summary(self) -> dict:
        with self._lock:
            out = {}
            for k, v in self._stages.items():
                vals = sorted(v)
                out[k] = {"n": len(vals), "mean_ms": round(statistics.fmean(vals), 1),
                          "p50_ms": round(vals[len(vals) // 2], 1),
                          "p95_ms": round(vals[min(len(vals) - 1, int(len(vals) * 0.95))], 1)}
            return {"latency": out, "counters": dict(self.counters)}


METRICS = Metrics()
