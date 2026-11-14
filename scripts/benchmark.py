"""CPU-only recognition benchmark. Run on UNO Q to obtain board-specific measurements."""
from __future__ import annotations
import argparse
import json
import platform
import sys
import time
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sonara.audio.wavio import read_wav, resample_linear
from sonara.config import load_config
from sonara.recognizer import Recognizer
from roles.speech.evaluation.memory import peak_process_rss_mib


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--wav', type=Path, required=True)
    ap.add_argument('--profile', default=None)
    ap.add_argument('--runs', type=int, default=30)
    ap.add_argument('--synthetic', action='store_true')
    ap.add_argument('--output', type=Path, default=Path('results/benchmark.json'))
    ap.add_argument("--config", type=Path)
    args = ap.parse_args()
    if not 1 <= args.runs <= 1000:
        ap.error('runs must be 1–1000')
    rec = Recognizer(load_config(args.config))
    if args.profile:
        rec.reload(args.profile)
    if not rec.ready:
        ap.error('enroll and load a profile before benchmarking')
    audio, sr = read_wav(args.wav)
    audio = resample_linear(audio, sr, 16000)
    try:
        rec.prepare(audio)
    except ValueError as exc:
        ap.error(str(exc))
    rec.recognize(audio)  # warm caches; capture is excluded from every timing
    elapsed = []
    cpu_start = time.process_time()
    for _ in range(args.runs):
        start = time.perf_counter()
        result = rec.recognize(audio)
        elapsed.append((time.perf_counter()-start)*1000)
    out = {'hardware': platform.platform(), 'machine': platform.machine(), 'python': platform.python_version(),
           'synthetic': args.synthetic, 'profile': rec.profile_id, 'counts': rec.clf.counts(),
           'runs': args.runs, 'audio_s': audio.size/16000,
           'processing_ms': {'mean': float(np.mean(elapsed)), 'p50': float(np.percentile(elapsed, 50)),
                             'p95': float(np.percentile(elapsed, 95)), 'max': max(elapsed)},
           'cpu_ms_per_run': (time.process_time()-cpu_start)*1000/args.runs,
           'peak_process_rss_mib': peak_process_rss_mib(),
           'template_mib': sum(s.nbytes for s in rec.clf.seqs)/1024**2,
           'last_prediction': result.to_dict(), 'note': 'Processing only; no capture or TTS. RSS is process high-water mark.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2, allow_nan=False))
    print(json.dumps(out, indent=2))


if __name__ == '__main__':
    main()
