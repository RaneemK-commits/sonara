"""Enroll a patient's personal phrases (few-shot), from the mic or from a folder of WAVs.

Live (records N takes per intent, stores ONLY embeddings):
  python scripts/enroll.py --takes 5
  python scripts/enroll.py --intents WATER PAIN --takes 3          # add/redo some phrases

Also keep the WAVs locally for evaluation (consented recordings only; never leave the board):
  python scripts/enroll.py --takes 8 --keep-audio --speaker alice

From a dataset folder  data/recordings/<speaker>/<INTENT>/*.wav :
  python scripts/enroll.py --from-dir data/recordings/alice --backend oww
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sonara.audio.wavio import read_wav, resample_linear, write_wav  # noqa: E402
from sonara.config import load_config  # noqa: E402
from sonara.models.classifier import PrototypeClassifier  # noqa: E402
from sonara.recognizer import Recognizer, profile_path  # noqa: E402


def iter_dir(root: Path, sr: int):
    for intent_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for wav in sorted(intent_dir.glob("*.wav")):
            audio, file_sr = read_wav(wav)
            yield intent_dir.name.upper(), resample_linear(audio, file_sr, sr), wav


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["oww", "mfcc"])
    ap.add_argument("--intents", nargs="*", help="subset of intent IDs (default: all)")
    ap.add_argument("--takes", type=int, default=5)
    ap.add_argument("--seconds", type=float, default=3.0, help="max seconds per take")
    ap.add_argument("--keep-audio", action="store_true")
    ap.add_argument("--speaker", default="patient")
    ap.add_argument("--from-dir", type=Path)
    ap.add_argument("--fresh", action="store_true", help="discard existing profile")
    args = ap.parse_args()

    cfg = load_config()
    sr = cfg.section("audio").get("sample_rate", 16000)
    rec = Recognizer(cfg, args.backend)
    clf = rec.clf if not args.fresh else PrototypeClassifier(rec.backend, rec.clf.matcher)
    wanted = [i.upper() for i in args.intents] if args.intents else [i.id for i in cfg.intents]

    if args.from_dir:
        for intent, audio, wav in iter_dir(args.from_dir, sr):
            if intent in wanted and (seq := rec.embed(audio)) is not None:
                clf.add(intent, seq)
    else:
        from sonara.audio.capture import AudioCapture

        a = cfg.section("audio")
        cap = AudioCapture(sr, a.get("block_ms", 30), a.get("device"), args.seconds,
                           a.get("silence_end_ms", 700), a.get("speech_start_factor", 3.0))
        time.sleep(0.5)  # let the noise floor settle
        for intent_id in wanted:
            intent = cfg.intent(intent_id)
            clf.remove_label(intent_id)  # re-enrolling replaces old takes
            print(f"\n=== {intent_id}: say your phrase for “{intent.speak}” ===")
            n = 0
            while n < args.takes:
                input(f"  take {n + 1}/{args.takes} — press Enter, then speak… ")
                cap.flush()
                audio = cap.record_utterance(wait_s=4.0)
                seq = rec.embed(audio) if audio is not None else None
                if seq is None:
                    print("  (no speech detected, try again)")
                    continue
                clf.add(intent_id, seq)
                if args.keep_audio:
                    out = cfg.path("data/recordings") / args.speaker / intent_id / f"{int(time.time()*1000)}.wav"
                    write_wav(out, audio, sr)
                n += 1
        cap.close()

    thr = clf.calibrate()
    path = profile_path(cfg, rec.backend)
    clf.save(path)
    print(f"\nsaved {path}.npz — counts {clf.counts()} — auto threshold {thr:.4f}")
    print("(no raw audio stored in the profile)")


if __name__ == "__main__":
    main()
