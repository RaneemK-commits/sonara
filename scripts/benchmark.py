"""On-device latency + energy benchmark. Run ON THE UNO Q for numbers you can quote.

  python scripts/benchmark.py --wav data/recordings/alice/WATER/xxx.wav --runs 30 \
      --idle-watts 2.1 --active-watts 3.4      # watts read from a USB power meter

Without measured watts it prints latency only; never present estimated watts as measured.
Energy per interaction = active_watts × active_seconds + idle_watts × (remaining seconds).
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sonara.audio.vad import trim_silence  # noqa: E402
from sonara.audio.wavio import read_wav, resample_linear  # noqa: E402
from sonara.config import load_config  # noqa: E402
from sonara.recognizer import Recognizer  # noqa: E402


def stats(xs):
    xs = sorted(xs)
    return {"mean_ms": round(statistics.fmean(xs), 1), "p50_ms": round(xs[len(xs) // 2], 1),
            "p95_ms": round(xs[min(len(xs) - 1, int(len(xs) * .95))], 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", type=Path, required=True)
    ap.add_argument("--runs", type=int, default=30)
    ap.add_argument("--backend", choices=["oww", "mfcc"])
    ap.add_argument("--idle-watts", type=float)
    ap.add_argument("--active-watts", type=float)
    args = ap.parse_args()

    cfg = load_config()
    sr = cfg.section("audio").get("sample_rate", 16000)
    rec = Recognizer(cfg, args.backend)
    audio, fsr = read_wav(args.wav)
    audio = resample_linear(audio, fsr, sr)
    stages = {"vad_trim": [], "embed": [], "classify": [], "total": []}
    cpu0 = time.process_time()
    wall0 = time.perf_counter()
    for _ in range(args.runs):
        t0 = time.perf_counter()
        sp = trim_silence(audio, sr)
        t1 = time.perf_counter()
        seq = rec.embedder(sp)
        t2 = time.perf_counter()
        if rec.ready:
            rec.clf.predict(seq, rec.threshold, rec.margin)
        t3 = time.perf_counter()
        for k, dt in zip(stages, (t1 - t0, t2 - t1, t3 - t2, t3 - t0)):
            stages[k].append(dt * 1000)
    wall = time.perf_counter() - wall0
    cpu_util = (time.process_time() - cpu0) / wall / (os.cpu_count() or 1)
    out = {"backend": rec.backend, "audio_s": round(audio.size / sr, 2), "runs": args.runs,
           "cpu_count": os.cpu_count(), "avg_cpu_util_all_cores": round(cpu_util, 3),
           "stages": {k: stats(v) for k, v in stages.items()}}
    active_s = statistics.fmean(stages["total"]) / 1000
    if args.idle_watts and args.active_watts:
        out["energy_per_recognition_J"] = round(args.active_watts * active_s, 3)
        out["energy_source"] = "measured (USB power meter readings supplied)"
        out["idle_power_W"] = args.idle_watts
        out["idle_energy_per_day_Wh"] = round(args.idle_watts * 24, 1)
    else:
        out["energy_source"] = "not measured — supply --idle-watts/--active-watts"
    print(json.dumps(out, indent=2))
    Path("results").mkdir(exist_ok=True)
    (Path("results") / f"bench_{rec.backend}_{time.strftime('%H%M%S')}.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
