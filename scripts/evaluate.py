"""Deterministic evaluation on separate enrollment/test WAV directories, never tune on test.

ROOT/enrollment/INTENT/*.wav: >=5 examples per intent
ROOT/test/INTENT/*.wav: >=3 new examples per intent
ROOT/test/_UNKNOWN/*.wav: unrelated speech, room noise, etc.
Optional ROOT/calibration_unknown/*.wav is enrollment-only negative calibration.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import platform
import sys
import time
from collections import defaultdict
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sonara.audio.wavio import read_wav, resample_linear
from sonara.config import load_config
from sonara.models.classifier import Prediction
from sonara.recognizer import Recognizer
from roles.speech.evaluation.memory import peak_process_rss_mib


def load_dataset(root: Path, rec: Recognizer):
    enrollment, test = {}, {}
    hashes = {}
    manifest = []
    for split, target in (("enrollment", enrollment), ("test", test)):
        for folder in sorted((root / split).iterdir()):
            if not folder.is_dir():
                continue
            label = folder.name.upper()
            if label not in ("_UNKNOWN", "UNKNOWN") and rec.cfg.intent(label) is None:
                raise ValueError(f"unconfigured intent: {label}")
            target[label] = []
            for wav in sorted(folder.glob("*.wav")):
                audio, sr = read_wav(wav)
                audio = resample_linear(audio, sr, 16000)
                # Hash decoded canonical PCM, catching identical audio with different headers.
                digest = hashlib.sha256(np.round(audio * 32768).astype('<i4').tobytes()).hexdigest()
                if digest in hashes:
                    raise ValueError(f"reused audio (data leakage): {wav} and {hashes[digest]}")
                hashes[digest] = str(wav)
                target[label].append(audio)
                manifest.append({"split": split, "label": label, "path": str(wav), "audio_sha256": digest})
    if not enrollment or any(label.startswith('_') or label == 'UNKNOWN' for label in enrollment):
        raise ValueError("enrollment must contain only known intents")
    for label in enrollment:
        if len(test.get(label, [])) < 3:
            raise ValueError(f"need at least three held-out recordings for {label}")
    if not test.get('_UNKNOWN', []) and not test.get('UNKNOWN', []):
        raise ValueError("test/_UNKNOWN WAV recordings are required")
    unknown = []
    for wav in sorted((root / 'calibration_unknown').glob('*.wav')):
        audio, sr = read_wav(wav)
        audio = resample_linear(audio, sr, 16000)
        digest = hashlib.sha256(np.round(audio*32768).astype('<i4').tobytes()).hexdigest()
        if digest in hashes:
            raise ValueError(f"calibration audio reused: {wav}")
        hashes[digest] = str(wav)
        seq = rec.embed(audio)
        if seq is None:
            raise ValueError(f"invalid UNKNOWN calibration clip: {wav}")
        unknown.append(seq)
        manifest.append({"split": "calibration_unknown", "path": str(wav), "audio_sha256": digest})
    return enrollment, test, unknown, manifest


def evaluate(enrollment, test, rec, count, band, unknown):
    clf = rec.new_classifier()
    clf.band = band
    clf.margin = rec.margin
    for label, clips in enrollment.items():
        if len(clips) < count:
            raise ValueError(f"need {count} enrollment examples for {label}")
        for audio in clips[:count]:
            seq = rec.embed(audio)
            if seq is None:
                raise ValueError(f"invalid enrollment recording for {label}")
            clf.add(label, seq)
    start = time.perf_counter()
    clf.calibrate(unknown=unknown)
    calibration_ms = (time.perf_counter()-start)*1000
    known_n = correct = wrong = rejected = unknown_n = unknown_accept = 0
    confusion = defaultdict(lambda: defaultdict(int))
    latencies = []
    for label, clips in test.items():
        if label not in enrollment and label not in ('_UNKNOWN', 'UNKNOWN'):
            raise ValueError(f"test intent not enrolled: {label}")
        for audio in clips:
            start = time.perf_counter()
            seq = rec.embed(audio)
            pred = clf.predict(seq, rec.threshold, rec.margin) if seq is not None else Prediction(
                None, None, float('inf'), 0., 0., {}, reason='invalid recording')
            latencies.append((time.perf_counter()-start)*1000)
            is_unknown = label in ('_UNKNOWN', 'UNKNOWN')
            confusion['UNKNOWN' if is_unknown else label][pred.intent or 'UNKNOWN'] += 1
            if is_unknown:
                unknown_n += 1
                unknown_accept += pred.accepted
            else:
                known_n += 1
                rejected += not pred.accepted
                correct += pred.intent == label
                wrong += pred.accepted and pred.intent != label
    return {"known_test_count": known_n, "unknown_test_count": unknown_n,
            "correct_intent_rate": correct / known_n,
            "accuracy_among_accepted_known": correct/(correct+wrong) if correct+wrong else None,
            "accuracy_among_all_accepted": correct/(correct+wrong+unknown_accept) if correct+wrong+unknown_accept else None,
            "known_rejection_rate": rejected/known_n,
            "overall_rejection_rate": (rejected+unknown_n-unknown_accept)/(known_n+unknown_n),
            "false_accept_other_known": wrong/known_n, "false_accept_unknown": unknown_accept/unknown_n,
            "confusion_matrix": {k: dict(v) for k, v in confusion.items()},
            "latency_ms": {"mean": float(np.mean(latencies)), "p50": float(np.percentile(latencies, 50)),
                           "p95": float(np.percentile(latencies, 95)), "max": max(latencies)},
            "peak_process_rss_mib": peak_process_rss_mib(),
            "template_mib": sum(s.nbytes for s in clf.seqs)/1024**2,
            "calibration_ms": calibration_ms, "calibration": clf.calibration}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('dataset', type=Path)
    ap.add_argument('--enroll-counts', type=int, nargs='+', default=[5])
    ap.add_argument('--bands', type=float, nargs='+', default=[.2])
    ap.add_argument('--simulated', action='store_true')
    ap.add_argument('--synthetic', action='store_true')
    ap.add_argument('--output', type=Path, default=Path('results/evaluation.json'))
    ap.add_argument("--config", type=Path)
    args = ap.parse_args()
    rec = Recognizer(load_config(args.config))
    try:
        enrollment, test, unknown, manifest = load_dataset(args.dataset, rec)
        out = {"dataset": str(args.dataset), "synthetic": args.synthetic, "simulated": args.simulated,
               "validation": "software only" if args.synthetic else "held-out recordings; not clinical validation",
               "hardware": platform.platform(), "machine": platform.machine(),
               "feature_config": rec.feature_config.to_dict(), "manifest": manifest, "systems": {}}
        for count in args.enroll_counts:
            if not 2 <= count <= 10:
                raise ValueError("enrollment count must be 2–10")
            for band in args.bands:
                if not 0 <= band <= 1:
                    raise ValueError('bands must be in [0, 1]')
                key = f'mfcc-dtw-k{count}-band{band}'
                out['systems'][key] = evaluate(enrollment, test, rec, count, band, unknown)
    except (ValueError, OSError) as exc:
        ap.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2, allow_nan=False))
    print(json.dumps({k: {m: v for m, v in r.items() if m not in ('calibration', 'confusion_matrix')}
                      for k, r in out['systems'].items()}, indent=2))
    print(f'Saved {args.output}. Synthetic/simulated recordings are not patient validation.')


if __name__ == '__main__':
    main()
