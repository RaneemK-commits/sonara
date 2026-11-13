"""Enroll on the device mic or import consented WAVs. Prefer /room for touchscreen setup."""
from __future__ import annotations
import argparse
import sys
import hashlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sonara.audio.wavio import read_wav, resample_linear, write_wav
from sonara.config import load_config
from sonara.models.classifier import PrototypeClassifier
from sonara.recognizer import Recognizer, profile_path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", default="patient_001")
    ap.add_argument("--intents", nargs="+")
    ap.add_argument("--takes", type=int, default=5)
    ap.add_argument("--seconds", type=float, default=3.)
    ap.add_argument("--automatic", action="store_true", help="VAD boundaries instead of fixed capture")
    ap.add_argument("--keep-audio", action="store_true")
    ap.add_argument("--from-dir", type=Path)
    ap.add_argument("--replace", action="store_true", help="replace selected intents, preserving others")
    ap.add_argument("--delete-intent")
    ap.add_argument("--config", type=Path)
    args = ap.parse_args()
    if not 1 <= args.takes <= 10 or not .3 <= args.seconds <= 5:
        ap.error("takes must be 1–10; seconds must be 0.3–5")
    cfg = load_config(args.config)
    rec = Recognizer(cfg)
    path = profile_path(cfg, args.profile)
    clf = PrototypeClassifier.load(path) if path.exists() else rec.new_classifier()
    clf.profile_id = args.profile
    rec.feature_config, rec.embedder.config = clf.feature_config, clf.feature_config
    wanted = args.intents or [i.id for i in cfg.request_intents]
    if any(cfg.intent(i) is None for i in wanted):
        ap.error("intent is not defined in config/intents.toml")
    if args.delete_intent:
        clf.remove_label(args.delete_intent)
        wanted = []
    if args.replace:
        for label in wanted:
            clf.remove_label(label)

    def add(label, audio):
        seq = rec.embed(audio, manual=not args.automatic)
        if seq is None:
            print(f"Rejected {label}: invalid, silent, clipped or too short. Repeat recording.")
            return False
        clf.add(label, seq)
        if args.keep_audio:
            write_wav(path / "recordings" / label / f"{hashlib.sha256(seq.tobytes()).hexdigest()}.wav", audio, 16000)
        return True

    if args.from_dir:
        for label in wanted:
            files = sorted((args.from_dir / label).glob("*.wav"))[:args.takes]
            for wav in files:
                audio, sr = read_wav(wav)
                add(label, resample_linear(audio, sr, 16000))
    elif wanted:
        from sonara.audio.capture import AudioCapture
        cap = AudioCapture(device=cfg.section("audio").get("device"), silence_end_ms=1200)
        try:
            for label in wanted:
                print(f"{label}: {cfg.intent(label).speak} — use your natural voice")
                count = 0
                while count < args.takes:
                    input(f"Take {count+1}/{args.takes}: Enter, then speak…")
                    cap.flush()
                    audio = cap.record_utterance(4.) if args.automatic else cap.record_manual(args.seconds)
                    if audio is not None and add(label, audio):
                        count += 1
        finally:
            cap.close()
    if wanted and not any(clf.counts().get(label, 0) for label in wanted):
        ap.error("no valid enrollment recordings were saved")
    clf.calibrate()
    clf.save(path)
    rec.reload(args.profile)
    print(f"Saved {path}: {clf.counts()}")
    for label, detail in clf.calibration.get("intents", {}).items():
        print(f"{label}: {detail.get('status', 'uncalibrated')}; "
              f"own p90={detail['positive_p90']}, other p10={detail['negative_p10']}, "
              f"threshold={detail['threshold']:.3f}, LOO gap p10={detail.get('loo_gap_p10')}")
    if clf.calibration.get("requires_more_recordings"):
        print("WARNING: Enrollment is not reliably separated. Test before use. "
              "Repeat inconsistent/noisy takes or choose more distinct natural vocalizations; "
              "adding the same poor recordings or raising thresholds alone will not fix overlap.")


if __name__ == "__main__":
    main()
