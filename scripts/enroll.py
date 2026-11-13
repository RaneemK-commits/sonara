"""Enroll on the device mic or import consented WAVs. Prefer /room for touchscreen setup."""
from __future__ import annotations
import argparse
import sys
import hashlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sonara.audio.wavio import read_wav, resample_linear, write_wav
from sonara.config import Config, load_config
from sonara.models.classifier import PrototypeClassifier
from sonara.recognizer import Recognizer, profile_path


def enroll_keywords(args: argparse.Namespace, cfg: Config) -> Path:
    """Create a separate feature-only keyword profile; never activate a patient."""
    from sonara.models.keywords import KeywordSpotter
    import socket
    if args.replace or args.delete_intent:
        raise ValueError('keyword mode creates a complete separate profile; use --keyword-overwrite explicitly')
    if args.takes<5 and not (args.from_dir and args.allow_few_shot):
        raise ValueError('keyword enrollment requires at least five real takes per word')
    scan_s=getattr(args,'keyword_scan_s',None)
    if scan_s is not None and not .25<=scan_s<=2:raise ValueError('keyword scan interval must be 0.25–2 seconds')
    profile_id=profile_path(cfg,args.profile).name
    directory=cfg.path(args.keyword_dir)/profile_id
    if directory.exists() and not args.keyword_overwrite:
        raise ValueError('keyword profile exists; choose another ID or use --keyword-overwrite')
    wanted=args.intents or [i.id for i in cfg.request_intents]
    if len(set(wanted))<2 or len(set(wanted))!=len(wanted):
        raise ValueError('choose at least two distinct request keywords')
    if any(cfg.intent(label) is None or cfg.intent(label).control for label in wanted):
        raise ValueError('keyword mode enrolls configured request intents, not ambient YES/NO controls')
    if not 0<=args.synthetic_variants<=5 or args.takes+args.synthetic_variants>10:
        raise ValueError('maximum ten references per word, with zero to five optional synthetic variants')
    recordings={label:[] for label in wanted};retained={label:[] for label in wanted}
    def accept(label,audio):
        prepared=KeywordSpotter.prepare_enrollment(audio,not args.preserve_word_boundaries)
        if any(hashlib.sha256(prepared.tobytes()).digest()==hashlib.sha256(a.tobytes()).digest()
               for a in recordings[label]):raise ValueError('duplicate source; record a new take')
        recordings[label].append(prepared)
        if args.keep_audio:retained[label].append(audio)
        rms=float((prepared.astype('float64')**2).mean()**.5)
        feedback='quiet recording; test carefully' if rms<.002 else 'level valid'
        print(f'{label}: {len(recordings[label])}/{args.takes} valid; word span {len(prepared)/16000:.2f} s; {feedback}')
    if args.from_dir:
        for label in wanted:
            folder=args.from_dir/label
            files=sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower()=='.wav') if folder.exists() else []
            for wav in files:
                if len(recordings[label])>=args.takes:break
                try:
                    audio,sr=read_wav(wav);accept(label,resample_linear(audio,sr,16000))
                except (ValueError,OSError) as exc:print(f'Skipped {wav.name}: {exc}')
            if len(recordings[label])!=args.takes:
                raise ValueError(f'{label}: need {args.takes} valid independent WAV files; found {len(recordings[label])}')
    else:
        # CLI capture must not compete with the server's persistent microphone owner.
        with socket.socket() as probe:
            probe.settimeout(.25)
            if probe.connect_ex(('127.0.0.1',cfg.section('server').get('port',8000)))==0:
                raise ValueError('stop the local Sonara server before direct CLI microphone enrollment; WAV import can run alongside it')
        from sonara.audio.capture import AudioCapture
        cap=AudioCapture(device=cfg.section('audio').get('device'))
        try:
            for label in wanted:
                print(f'{label}: {cfg.intent(label).speak} — use your natural personal sound')
                while len(recordings[label])<args.takes:
                    input(f'Take {len(recordings[label])+1}/{args.takes}: Enter, then speak…')
                    cap.flush()
                    audio=cap.record_utterance(4.) if args.automatic else cap.record_manual(args.seconds)
                    try:
                        if audio is None:raise ValueError('no speech captured')
                        accept(label,audio)
                    except ValueError as exc:print(f'Repeat: {exc}')
        finally:cap.close()
    model=KeywordSpotter.enroll(recordings,trim_endpoints=False,synthetic_per_intent=args.synthetic_variants,
                                 seed=42,allow_few_shot=args.allow_few_shot,
                                 augmentation_policy=getattr(args,'augmentation_policy',None) or 'balanced20',
                                 alignment_stride=2 if getattr(args,'keyword_detail',False) else 3,
                                 stride_s=scan_s if scan_s is not None else (.5 if getattr(args,'keyword_detail',False) else .75))
    model.save(directory)
    if args.keep_audio:
        for label,clips in retained.items():
            for index,audio in enumerate(clips):write_wav(directory/'recordings'/label/f'{index:02d}.wav',audio,16000)
    print(f'Saved separate keyword profile: {directory}; active production profile unchanged')
    for label,detail in model.classifier.calibration['intents'].items():
        print(f"{label}: {detail['independent_recordings']} real + {detail['synthetic_variants']} synthetic; {detail['status']}")
    print('Test independent natural phrases and negative streams before live use. Confirmation remains required.')
    return directory


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
    ap.add_argument('--keyword-profile',action='store_true',help='create experimental keyword-in-phrase profile, separate from production')
    ap.add_argument('--keyword-detail',action='store_true',help='20 ms matching / 0.5 s scans for faster CPUs; default is 30 ms / 0.75 s')
    ap.add_argument('--keyword-scan-s',type=float,help='scan interval in seconds; e.g. 1.25 reduces UNO Q CPU load')
    ap.add_argument('--keyword-dir',default='data/keyword_profiles')
    ap.add_argument('--keyword-overwrite',action='store_true',help='explicitly replace a complete keyword profile')
    ap.add_argument('--synthetic-variants',type=int,default=0,help='optional keyword-only augmentation; not extra real takes')
    ap.add_argument('--augmentation-policy',choices=['balanced20','mild35'],default=None,help='keyword-only optional synthetic policy')
    ap.add_argument('--allow-few-shot',action='store_true',help='WAV-import experiments only; fewer than five real takes')
    ap.add_argument('--preserve-word-boundaries',action='store_true',help='keyword-only manual boundaries instead of endpoint trimming')
    args = ap.parse_args()
    if not 1 <= args.takes <= 10 or not .3 <= args.seconds <= 5:
        ap.error("takes must be 1–10; seconds must be 0.3–5")
    cfg = load_config(args.config)
    if args.keyword_profile:
        try:enroll_keywords(args,cfg)
        except (ValueError,OSError,RuntimeError) as exc:ap.error(str(exc))
        return
    if args.synthetic_variants or args.allow_few_shot or args.keyword_overwrite or args.preserve_word_boundaries or args.keyword_detail or args.augmentation_policy is not None or args.keyword_dir!='data/keyword_profiles' or args.keyword_scan_s is not None:
        ap.error('keyword-specific options require --keyword-profile')
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
