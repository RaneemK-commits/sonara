"""Recognition evaluation: personalised neural embeddings vs classical MFCC-DTW vs standard ASR.

Dataset layout (consented recordings; acted/simulated samples must be labelled as such):
  data/recordings/<speaker>/<INTENT>/*.wav       (+ optional <speaker>/_UNKNOWN/*.wav for
                                                   out-of-vocabulary speech/noise → rejection test)

  python scripts/evaluate.py data/recordings/alice --enroll 3 --systems oww-dtw oww-mean mfcc-dtw asr

For each system: repeated random splits (k enrollment takes per intent, rest held out) →
accuracy on accepted, rejection rate, false-accept rate, confusion matrix, per-utterance latency.
Writes results/eval_<speaker>_<time>.json and prints a markdown table for the README/pitch.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sonara.audio.vad import trim_silence  # noqa: E402
from sonara.audio.wavio import read_wav, resample_linear  # noqa: E402
from sonara.config import load_config  # noqa: E402
from sonara.models.classifier import PrototypeClassifier  # noqa: E402
from sonara.models.embedder import make_embedder  # noqa: E402

ASR_KEYWORDS = {  # what a standard recogniser would need to hear
    "HELP": ["help"], "WATER": ["water", "drink"], "FOOD": ["food", "eat", "hungry"],
    "PAIN": ["pain", "hurt", "hurts"], "BATHROOM": ["bathroom", "toilet", "restroom", "loo"],
    "YES": ["yes", "yeah"], "NO": ["no", "nope"],
}


def load_dataset(root: Path, sr: int):
    data = defaultdict(list)
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        for wav in sorted(d.glob("*.wav")):
            a, fsr = read_wav(wav)
            data[d.name.upper()].append(trim_silence(resample_linear(a, fsr, sr), sr))
    return data


def run_prototype(system, data, k, runs, cfg, margin):
    backend, matcher = system.split("-")
    emb = make_embedder(backend, cfg)
    t0 = time.perf_counter()
    feats = {lab: [emb(a) for a in clips] for lab, clips in data.items()}
    embed_ms = (time.perf_counter() - t0) * 1000 / sum(len(v) for v in data.values())
    rng = random.Random(0)
    res = new_result()
    cls_ms = []
    for _ in range(runs):
        clf = PrototypeClassifier(backend, matcher)
        test = []
        for lab, seqs in feats.items():
            if lab == "_UNKNOWN":
                test += [(None, s) for s in seqs]
                continue
            idx = list(range(len(seqs)))
            rng.shuffle(idx)
            for i in idx[:k]:
                clf.add(lab, seqs[i])
            test += [(lab, seqs[i]) for i in idx[k:]]
        clf.calibrate()
        for truth, seq in test:
            t = time.perf_counter()
            p = clf.predict(seq, margin=margin)
            cls_ms.append((time.perf_counter() - t) * 1000)
            score(res, truth, p.intent)
    return finish(res, embed_ms + float(np.mean(cls_ms)))


def run_asr(data, sr):
    from faster_whisper import WhisperModel  # optional baseline

    model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
    res, ms = new_result(), []
    for lab, clips in data.items():
        for a in clips:
            t = time.perf_counter()
            segs, _ = model.transcribe(a, language="en", beam_size=1)
            text = " ".join(s.text for s in segs).lower()
            ms.append((time.perf_counter() - t) * 1000)
            words = set(re.findall(r"[a-z']+", text))
            hits = [i for i, kw in ASR_KEYWORDS.items() if words & set(kw)]
            score(res, None if lab == "_UNKNOWN" else lab, hits[0] if len(hits) == 1 else None)
    return finish(res, float(np.mean(ms)))


def new_result():
    return {"n": 0, "correct": 0, "wrong": 0, "rejected": 0, "unk_n": 0, "unk_accepted": 0,
            "confusion": defaultdict(lambda: defaultdict(int))}


def score(res, truth, pred):
    if truth is None:
        res["unk_n"] += 1
        res["unk_accepted"] += pred is not None
        return
    res["n"] += 1
    res["confusion"][truth][pred or "REJECT"] += 1
    if pred is None:
        res["rejected"] += 1
    elif pred == truth:
        res["correct"] += 1
    else:
        res["wrong"] += 1


def finish(res, latency_ms):
    n = max(res["n"], 1)
    acc_n = res["correct"] + res["wrong"]
    return {
        "top1_accuracy": res["correct"] / n,
        "accuracy_when_accepted": res["correct"] / acc_n if acc_n else None,
        "rejection_rate": res["rejected"] / n,
        "false_accept_in_vocab": res["wrong"] / n,
        "false_accept_unknown": (res["unk_accepted"] / res["unk_n"]) if res["unk_n"] else None,
        "n_test": res["n"], "latency_ms_per_utt": round(latency_ms, 1),
        "confusion": {k: dict(v) for k, v in res["confusion"].items()},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset", type=Path)
    ap.add_argument("--enroll", type=int, default=3, help="takes per intent used for enrollment")
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--systems", nargs="+", default=["oww-dtw", "oww-mean", "mfcc-dtw"])
    ap.add_argument("--simulated", action="store_true", help="label results as acted/simulated speech")
    args = ap.parse_args()

    cfg = load_config()
    sr = cfg.section("audio").get("sample_rate", 16000)
    margin = cfg.section("recognition").get("margin", 0.05)
    data = load_dataset(args.dataset, sr)
    print({k: len(v) for k, v in data.items()})
    out = {"dataset": str(args.dataset), "simulated": args.simulated, "enroll_k": args.enroll,
           "runs": args.runs, "systems": {}}
    for s in args.systems:
        print(f"→ {s}")
        try:
            out["systems"][s] = run_asr(data, sr) if s == "asr" else run_prototype(
                s, data, args.enroll, args.runs, cfg, margin)
        except Exception as e:
            print(f"  skipped: {e}")
    Path("results").mkdir(exist_ok=True)
    path = Path("results") / f"eval_{args.dataset.name}_{time.strftime('%H%M%S')}.json"
    path.write_text(json.dumps(out, indent=2))
    print(f"\n| system | top-1 acc | acc when accepted | rejected | wrong | unknown accepted | ms/utt |")
    print("|---|---|---|---|---|---|---|")
    f = lambda x: "—" if x is None else f"{x:.0%}"
    for s, r in out["systems"].items():
        print(f"| {s} | {f(r['top1_accuracy'])} | {f(r['accuracy_when_accepted'])} | {f(r['rejection_rate'])} "
              f"| {f(r['false_accept_in_vocab'])} | {f(r['false_accept_unknown'])} | {r['latency_ms_per_utt']} |")
    print(f"\nsaved {path}" + ("  (SIMULATED speech — not patient-validated)" if args.simulated else ""))


if __name__ == "__main__":
    main()
