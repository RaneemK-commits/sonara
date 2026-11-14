"""Guided device-microphone enrollment and independent testing; no activation."""
from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from sonara.config import load_config
from sonara.recognizer import Recognizer, profile_path
from sonara.models.classifier import Prediction, PrototypeClassifier
from sonara.audio.wavio import write_wav

DEFAULT_INTENTS = ['WATER', 'HELP', 'FOOD', 'PAIN', 'BATHROOM', 'YES', 'NO']
UNKNOWN_PROMPTS = [
    'say: The window is open',
    'say: Today is Tuesday',
    'say: My shoes are blue',
    'say: Turn on the television',
    'remain silent and record ordinary room noise',
]

SIMILAR_WORDS = {
    'WATER': ['warmer', 'walker'], 'HELP': ['held', 'helmet'],
    'FOOD': ['foot', 'fool'], 'PAIN': ['paint', 'plane'],
    'BATHROOM': ['bedroom', 'bathrobe'], 'YES': ['yet', 'yell'],
    'NO': ['note', 'snow'],
}


def test_plan(intents, tests, unknown):
    plan = [{'expected': label, 'category': 'known', 'prompt': f'say {label}'}
            for _ in range(tests) for label in intents]
    plan += [{'expected': 'UNKNOWN', 'category': 'unrelated',
              'prompt': UNKNOWN_PROMPTS[i % len(UNKNOWN_PROMPTS)]} for i in range(unknown)]
    plan += [{'expected': 'UNKNOWN', 'category': 'similar_word',
              'near_intent': label, 'prompt': f'say: {word}'}
             for label in intents for word in SIMILAR_WORDS.get(label, [])]
    return plan


def record_until_enter(cap):
    """Drain the shared stream until Enter; bound memory and reject overlong takes."""
    import threading
    import numpy as np
    stopped = threading.Event()
    chunks, errors = [], []
    total = 0
    before = cap.dropped_blocks

    def read():
        nonlocal total
        try:
            while not stopped.is_set():
                block = cap.read_chunk(timeout_s=.1)
                if block is not None:
                    total += len(block)
                    if total <= 80000:
                        chunks.append(block)
        except Exception as exc:
            errors.append(exc)

    worker = threading.Thread(target=read, daemon=True)
    worker.start()
    try:
        input('RECORDING — press Enter to stop (Ctrl+C discards): ')
    finally:
        stopped.set()
        worker.join()
    if errors:
        raise RuntimeError(f'Microphone failed: {errors[0]}')
    if total > 80000:
        raise ValueError('Take exceeds the recognizer’s 5-second limit; please re-record a shorter take.')
    if cap.dropped_blocks != before:
        raise ValueError('Audio dropped during capture; please re-record.')
    if not chunks:
        raise ValueError('No audio captured; please re-record.')
    return np.concatenate(chunks).astype(np.float32)


def keep_take():
    while True:
        choice = input('Enter to keep, r to discard/re-record, q to stop: ').strip().lower()
        if choice in ('', 'r', 'q'):
            if choice == 'q':
                raise EOFError
            return choice == ''
        print('Use Enter, r or q.')


def run(args):
    cfg = load_config(args.config)
    path = profile_path(cfg, args.profile)
    if path.exists() and not args.test_only:
        raise ValueError('Profile already exists; choose a new --profile to preserve it.')
    if len(set(args.intents)) < 2 or len(set(args.intents)) != len(args.intents):
        raise ValueError('Choose at least two distinct intents.')
    if any(cfg.intent(x) is None for x in args.intents):
        raise ValueError('Choose configured intents, such as WATER, PAIN, YES and NO.')
    with socket.socket() as probe:
        probe.settimeout(.3)
        if probe.connect_ex(('127.0.0.1', cfg.section('server').get('port', 8000))) == 0:
            raise ValueError('Stop Sonara before recording: its server owns the microphone.')
    rec = Recognizer(cfg)
    if args.test_only:
        if not path.exists():
            raise ValueError('Profile does not exist; enroll first.')
        model = PrototypeClassifier.load(path)
        args.intents = model.classes
    else:
        model = rec.new_classifier()
    model.profile_id = args.profile
    # Use the new profile configuration, independent of any active old profile.
    from sonara.models.embedder import MFCCEmbedder
    embedder = MFCCEmbedder(model.feature_config)
    from sonara.audio.capture import AudioCapture
    device = None if args.device == 'default' else (args.device or cfg.section('audio').get('device'))
    cap = AudioCapture(device=device)
    rows = []
    print('Say each word naturally, once per recording. Small natural variation is welcome.')
    print('Speak after RECORDING. Keep the microphone position steady. No voice imitation required.')
    print('Enter starts each take; Enter stops it. Keep each word recording within 5 seconds.')

    def capture(prompt):
        while True:
            choice = input(prompt + ' — Enter to record, q to stop: ').strip().lower()
            if choice == 'q':
                raise EOFError
            cap.flush()
            try:
                if args.seconds is None:
                    audio = record_until_enter(cap)
                else:
                    print(f'RECORDING for {args.seconds:g} seconds...', flush=True)
                    audio = cap.record_manual(args.seconds)
            except ValueError as exc:
                print(exc)
                continue
            except KeyboardInterrupt:
                print('Take discarded. Press Enter to re-record or q to stop.')
                continue
            print('Recording complete.')
            return audio

    try:
        if not args.test_only:
            for label in args.intents:
                for index in range(args.takes):
                    while True:
                        audio = capture(f'ENROLL {label} {index + 1}/{args.takes}')
                        try:
                            speech, quality = rec.prepare(audio, manual=True)
                            seq = embedder(speech)
                        except (ValueError, TypeError) as exc:
                            print(f'Invalid take: {exc}. Repeat.'); continue
                        print(quality)
                        if not keep_take():
                            continue
                        model.add(label, seq)
                        if args.keep_audio:
                            write_wav(path / 'recordings' / 'enrollment' / label / f'{index:02d}.wav', audio, 16000)
                        break
            model.calibrate()
            model.save(path)
            print('Saved separate profile; active profile unchanged.')
            print(json.dumps(model.calibration, indent=2))
        print('TEST: new recordings only. Results never modify calibration or send requests.')
        from datetime import datetime, timezone
        from uuid import uuid4
        run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid4().hex[:8]
        test_directory = path / 'test_runs' / run_id
        test_directory.mkdir(parents=True, exist_ok=False)
        trials = test_plan(args.intents, args.tests, args.unknown)
        if args.similar_only:
            trials = [trial for trial in trials if trial['category'] == 'similar_word']
        for index, trial in enumerate(trials):
            label, hint = trial['expected'], trial['prompt']
            while True:
                audio = capture(f'TEST {index + 1}: {hint}')
                # Decide before seeing prediction to avoid selecting only successful tests.
                if keep_take():
                    break
            try:
                speech, quality = rec.prepare(audio, manual=True)
                pred = model.predict(embedder(speech), rec.threshold, rec.margin)
            except (ValueError, TypeError) as exc:
                pred = Prediction(None, None, float('inf'), 0., model.threshold, {}, reason=str(exc))
            row = {**trial, **pred.to_dict()}
            rows.append(row)
            print(json.dumps(row))
            if args.keep_audio:
                write_wav(test_directory / 'recordings' / label / f'{index:02d}.wav', audio, 16000)
            report = summarize(rows)
            (test_directory / 'demo_test.json').write_text(json.dumps({'trials': rows, 'summary': report}, indent=2))
        print(json.dumps(summarize(rows), indent=2))
        print(f'Report: {test_directory / "demo_test.json"}. Profile NOT activated. Review before loading through /room.')
    finally:
        cap.close()


def summarize(rows):
    known = [r for r in rows if r['expected'] != 'UNKNOWN']
    unknown = [r for r in rows if r['expected'] == 'UNKNOWN']
    accepted = [r for r in rows if r['accepted']]
    correct = sum(r['intent'] == r['expected'] for r in known)
    return {'known_trials': len(known), 'correct_accepted': correct,
            'wrong_intent_accepts': sum(r['accepted'] and r['intent'] != r['expected'] for r in known),
            'known_rejections': sum(not r['accepted'] for r in known),
            'similar_word_trials': sum(r.get('category') == 'similar_word' for r in unknown),
            'similar_word_false_accepts': sum(r['accepted'] and r.get('category') == 'similar_word' for r in unknown),
            'unknown_trials': len(unknown), 'unknown_false_accepts': sum(r['accepted'] for r in unknown),
            'accepted_precision': correct / len(accepted) if accepted else None,
            'known_recall': correct / len(known) if known else None,
            'warning': 'Small personal demo test, not general accuracy or clinical validation.'}


def record_only(args):
    """Collect labeled WAVs without loading, fitting or evaluating a voice profile."""
    from datetime import datetime, timezone
    from uuid import uuid4
    from sonara.audio.capture import AudioCapture
    cfg = load_config(args.config)
    root = profile_path(cfg, args.profile) / 'recording_sessions'
    directory = root / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid4().hex[:8])
    with socket.socket() as probe:
        probe.settimeout(.3)
        if probe.connect_ex(('127.0.0.1', cfg.section('server').get('port', 8000))) == 0:
            raise ValueError('Stop Sonara before recording; its server owns the microphone.')
    device = None if args.device == 'default' else (args.device or cfg.section('audio').get('device'))
    cap = AudioCapture(device=device)
    plan = test_plan(args.intents, args.tests, args.unknown)
    if args.similar_only:
        plan = [trial for trial in plan if trial['category'] == 'similar_word']
    saved = []
    try:
        for index, trial in enumerate(plan):
            while True:
                if input(f"RECORD {index + 1}/{len(plan)}: {trial['prompt']} — Enter to start, q to quit: ").strip().lower() == 'q':
                    raise EOFError
                cap.flush()
                try:
                    audio = record_until_enter(cap) if args.seconds is None else cap.record_manual(args.seconds)
                except (ValueError, KeyboardInterrupt) as exc:
                    print(f'Take discarded. {exc}')
                    continue
                if not keep_take():
                    continue
                directory.mkdir(parents=True, exist_ok=True)
                filename = f'{index:03d}.wav'
                write_wav(directory / filename, audio, 16000)
                saved.append({**trial, 'file': filename, 'duration_s': len(audio) / 16000})
                (directory / 'manifest.json').write_text(json.dumps(saved, indent=2))
                print(f'SAVED: {directory / filename}', flush=True)
                break
    finally:
        cap.close()
        print(f'{len(saved)} recordings saved in {directory}')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--profile', required=True)
    p.add_argument('--record-only', action='store_true', help='save labeled WAVs only; no profile or recognition required')
    p.add_argument('--test-only', action='store_true', help='test an existing saved profile without re-enrolling')
    p.add_argument('--intents', nargs='+', default=DEFAULT_INTENTS,
                   help='request words to enroll (default: WATER HELP FOOD PAIN BATHROOM YES NO)')
    p.add_argument('--similar-only', action='store_true', help='record similar-word tests using an existing profile (implies --test-only)')
    p.add_argument('--takes', type=int, default=5)
    p.add_argument('--tests', type=int, default=3)
    p.add_argument('--unknown', type=int, default=5)
    p.add_argument('--seconds', type=float, help='optional fixed duration; omit to stop with Enter')
    p.add_argument('--device', help='default = laptop default microphone; otherwise device name')
    p.add_argument('--config', type=Path)
    p.add_argument('--keep-audio', action='store_true', help='opt in to saving local WAVs for diagnosis')
    args = p.parse_args()
    if args.similar_only:
        args.test_only = True
    if not 5 <= args.takes <= 10 or not 1 <= args.tests <= 20 or not 1 <= args.unknown <= 20 or (args.seconds is not None and not .3 <= args.seconds <= 5):
        p.error('takes 5–10, tests/unknown 1–20, seconds 0.3–5 required')
    try:
        if args.record_only:
            record_only(args)
        else:
            run(args)
    except (ValueError, RuntimeError, OSError) as exc:
        p.exit(1, f'{exc}\n')
    except (KeyboardInterrupt, EOFError):
        p.exit(130, '\nStopped. Active profile unchanged.\n')


if __name__ == '__main__':
    main()
