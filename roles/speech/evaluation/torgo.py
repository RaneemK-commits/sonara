"""Pinned TORGO subset preparation (laptop) and isolated offline evaluation (CPU).

Never downloads neural weights, records a patient, or contacts Sonara's live server.
Optional HF/PyArrow/SoundFile dependencies are imported only by the prepare command.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import platform
import re
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from sonara.audio.wavio import read_wav, write_wav
from sonara.config import Config, Intent, load_config
from sonara.recognizer import Recognizer, profile_path
from roles.speech.evaluation.evaluate_real_corpus import checked_path
from roles.speech.evaluation.memory import peak_process_rss_mib
from roles.speech.evaluation.prepare_real_corpus import bounded_audio, pcm_hash

REPOSITORY = 'abnerh/TORGO-database'
REVISION = '6e9b33c1af30eb3878574a1c1f5e60a60bd6d9c5'
WORDS = ('yes', 'no', 'sip', 'sigh', 'leak')
# All dysarthric speakers with >=3 eligible headMic takes of every fixed word.
SPEAKERS = ('F03', 'M01', 'M02', 'M03', 'M05')
FILENAME = re.compile(r'(?P<speaker>[FM]C?\d+)_(?P<session>\d+)_(?P<mic>arrayMic|headMic)_(?P<utterance>\d+)\.wav$')


def source_info(filename: str) -> dict[str, str]:
    match = FILENAME.fullmatch(Path(filename).name)
    if match is None:
        raise ValueError(f'unrecognized TORGO filename: {filename}')
    return match.groupdict()


def take_key(row: dict) -> tuple[str, str, str]:
    info = source_info(row['file'])
    return info['speaker'], info['session'], info['utterance']


def word(row: dict) -> str:
    return ' '.join(row['transcription'].casefold().split())


def select(rows: list[dict]) -> dict:
    """Freeze a metadata-only protocol before any matching scores are calculated.

    Two independent enrollment takes, remaining 1–3 held-out takes per word.
    Ten other-word UNKNOWNs and five same-word impostor trials per other speaker.
    """
    eligible = [r for r in rows if source_info(r['file'])['mic'] == 'headMic'
                and .3 <= r['duration'] <= 5 and r['speech_status'] == 'dysarthria']
    eligible.sort(key=lambda r: take_key(r))
    keys = [take_key(r) for r in eligible]
    if len(keys) != len(set(keys)):
        raise ValueError('duplicate source take in metadata')
    profiles = []
    for speaker in SPEAKERS:
        own = [r for r in eligible if take_key(r)[0] == speaker]
        refs, queries = [], []
        for label in WORDS:
            takes = [r for r in own if word(r) == label]
            if len(takes) < 3:
                raise ValueError(f'{speaker}/{label}: need at least three independent takes')
            refs.extend({**r, 'label': label.upper(), 'category': 'enrollment'} for r in takes[:2])
            queries.extend({**r, 'label': label.upper(), 'category': 'known'} for r in takes[2:5])
        # Deterministic hash order avoids choosing unknowns by acoustic distance.
        others = [r for r in own if word(r) not in WORDS and len(word(r).split()) == 1]
        others.sort(key=lambda r: hashlib.sha256(r['file'].encode()).hexdigest())
        queries.extend({**r, 'label': 'UNKNOWN', 'category': 'unknown'} for r in others[:10])
        for other in SPEAKERS:
            if other == speaker:
                continue
            for label in WORDS:
                # Last take is held out in that speaker's own profile as well.
                candidates = [r for r in eligible if take_key(r)[0] == other and word(r) == label]
                queries.append({**candidates[-1], 'label': 'UNKNOWN', 'category': 'impostor'})
        profiles.append({'speaker': speaker, 'references': refs, 'queries': queries})
    return {'version': 1, 'repository': REPOSITORY, 'revision': REVISION,
            'words': list(WORDS), 'profiles': profiles,
            'protocol': 'headMic only; first two takes per word enroll; next up to three test; no test threshold tuning',
            'warning': 'Small corpus experiment with two enrollment takes, not Sonara request accuracy or speaker verification.'}


def validate(manifest: dict) -> None:
    if manifest['repository'] != REPOSITORY or manifest['revision'] != REVISION:
        raise ValueError('unexpected corpus revision')
    if [p['speaker'] for p in manifest['profiles']] != list(SPEAKERS):
        raise ValueError('unexpected or duplicate evaluation speakers')
    for profile in manifest['profiles']:
        seen, hashes = set(), set()
        refs = profile['references']
        if Counter(r['label'] for r in refs) != Counter({w.upper(): 2 for w in WORDS}):
            raise ValueError('expected two independent enrollment takes per word')
        for entry in refs + profile['queries']:
            if entry['category'] not in ('enrollment', 'known', 'unknown', 'impostor'):
                raise ValueError('unknown trial category')
            if entry['category'] == 'unknown' and word(entry) in WORDS:
                raise ValueError('UNKNOWN must be an unenrolled word')
            info = source_info(entry['file'])
            key = take_key(entry)
            digest = entry.get('source_pcm_sha256')
            if info['mic'] != 'headMic' or key in seen or (digest and digest in hashes):
                raise ValueError('duplicate take/channel/PCM: possible enrollment/test leakage')
            seen.add(key)
            if digest:
                hashes.add(digest)
            if entry['category'] != 'impostor' and info['speaker'] != profile['speaker']:
                raise ValueError('speaker mismatch')
            if entry['category'] == 'impostor' and info['speaker'] == profile['speaker']:
                raise ValueError('impostor must be another speaker')
            expected = word(entry).upper() if entry['category'] in ('enrollment', 'known') else 'UNKNOWN'
            if entry['label'] != expected or (expected != 'UNKNOWN' and word(entry) not in WORDS):
                raise ValueError('label/transcript mismatch')
            if entry.get('kind', 'complete_utterance') != 'complete_utterance':
                raise ValueError('whole utterances required')


def audit(directory: Path) -> list[dict]:
    """Read only nested filenames and text; binary audio stays on the hub."""
    from huggingface_hub import HfFileSystem
    import pyarrow.parquet as pq
    directory.mkdir(parents=True, exist_ok=True)
    fs = HfFileSystem(token=False)
    rows = []
    for shard_index in range(4):
        shard = f'data/train-{shard_index:05d}-of-00004.parquet'
        print(f'auditing {shard}', flush=True)
        with fs.open(f'datasets/{REPOSITORY}@{REVISION}/{shard}', 'rb', block_size=262144) as stream:
            parquet = pq.ParquetFile(stream)
            for group in range(parquet.num_row_groups):
                table = parquet.read_row_group(group, columns=['audio.path', 'transcription', 'speech_status', 'duration', 'severity'])
                for index, row in enumerate(table.to_pylist()):
                    name = Path(row.pop('audio')['path']).name
                    rows.append({'file': name, 'shard': shard, 'row_group': group,
                                 'group_index': index, **source_info(name), **row})
    (directory/'rows.json').write_text(json.dumps(rows, indent=2))
    (directory/'revision.json').write_text(json.dumps({'repository': REPOSITORY, 'revision': REVISION}))
    return rows


def prepare(directory: Path) -> dict:
    from huggingface_hub import HfFileSystem
    import pyarrow.parquet as pq
    import soundfile as sf
    from scipy.signal import resample_poly
    from math import gcd

    directory.mkdir(parents=True, exist_ok=True)
    marker = directory/'revision.json'
    hub = directory/'hub.json'
    cached_revision = (json.loads(marker.read_text()).get('revision') if marker.exists()
                       else json.loads(hub.read_text()).get('sha') if hub.exists() else None)
    metadata = (json.loads((directory/'rows.json').read_text())
                if (directory/'rows.json').exists() and cached_revision == REVISION else audit(directory))
    manifest = select(metadata)
    validate(manifest)
    bundle = directory/'bundle'
    bundle.mkdir(exist_ok=True)
    # Persist selection before downloading/decoding: audio quality cannot change the split.
    (directory/'selection.json').write_text(json.dumps(manifest, indent=2))
    groups = defaultdict(dict)
    for profile in manifest['profiles']:
        for entry in profile['references'] + profile['queries']:
            groups[entry['shard'], entry['row_group']][entry['file']] = entry
    fs = HfFileSystem(token=False)
    converted = {}
    for (shard, group), selected in sorted(groups.items()):
        missing = {name: entry for name, entry in selected.items() if not (bundle/name).exists()}
        if missing:
            print(f'downloading {shard}, group {group}: {len(missing)} selected takes', flush=True)
            with fs.open(f'datasets/{REPOSITORY}@{REVISION}/{shard}', 'rb', block_size=262144) as stream:
                table = pq.ParquetFile(stream).read_row_group(group, columns=['audio'])
                for name, entry in missing.items():
                    audio = table['audio'][entry['group_index']].as_py()
                    if Path(audio['path']).name != name or not audio['bytes']:
                        raise ValueError('metadata/audio row mismatch')
                    raw = audio['bytes']
                    if not 0 < sf.info(io.BytesIO(raw)).duration <= 120:
                        raise ValueError('invalid source duration')
                    samples, sr = sf.read(io.BytesIO(raw), dtype='float32', always_2d=True)
                    samples = samples.mean(axis=1)
                    if sr != 16000:
                        divisor = gcd(sr, 16000)
                        samples = resample_poly(samples, 16000//divisor, sr//divisor).astype(np.float32)
                    # No cropping to fit: complete endpoint-trimmed utterances only.
                    try:
                        clip, segmentation = bounded_audio(samples, 16000, False)
                    except ValueError as exc:
                        # Preserve invalid trials and denominator; never silently replace a take.
                        clip = samples
                        segmentation = {'kind': 'complete_utterance', 'preparation_error': str(exc)}
                    write_wav(bundle/name, clip, 16000)
                    (bundle/(name+'.json')).write_text(json.dumps(segmentation))
            del table
        for name in selected:
            audio, sr = read_wav(bundle/name)
            if sr != 16000:
                raise ValueError('expected 16 kHz bundle')
            converted[name] = {'source_pcm_sha256': pcm_hash(audio),
                               'wav_sha256': hashlib.sha256((bundle/name).read_bytes()).hexdigest(),
                               **json.loads((bundle/(name+'.json')).read_text())}
    for profile in manifest['profiles']:
        for entry in profile['references'] + profile['queries']:
            entry.update(converted[entry['file']])
    validate(manifest)
    (bundle/'manifest.json').write_text(json.dumps(manifest, indent=2, allow_nan=False))
    print(f'Prepared {len(converted)} distinct complete takes: {bundle}', flush=True)
    return manifest


def metrics(rows: list[dict]) -> dict:
    known = [r for r in rows if r['category'] == 'known']
    accepted = [r for r in known if r['accepted']]
    correct = sum(r['intent'] == r['truth'] for r in known)
    times = [r['latency_ms'] for r in rows]
    confusion = defaultdict(Counter)
    for row in rows:
        confusion[row['truth']][row['intent'] or 'UNKNOWN'] += 1
    ratio = lambda n, total: n/total if total else None
    result = {'known_trials': len(known), 'correct_intent_rate': ratio(correct, len(known)),
              'nearest_intent_correct_rate_before_rejection': ratio(sum(r['best'] == r['truth'] for r in known), len(known)),
              'accuracy_among_accepted_known': ratio(correct, len(accepted)),
              'known_rejection_rate': ratio(sum(not r['accepted'] for r in known), len(known)),
              'wrong_known_intent_acceptance_rate': ratio(sum(r['accepted'] and r['intent'] != r['truth'] for r in known), len(known)),
              'invalid_audio_count': sum(not r['valid_audio'] for r in rows),
              'confusion_matrix': {k: dict(v) for k, v in confusion.items()},
              'latency_ms': ({'mean': float(np.mean(times)), 'p95': float(np.percentile(times, 95)), 'max': max(times)} if times else None)}
    for category in ('unknown', 'impostor'):
        subset = [r for r in rows if r['category'] == category]
        result[category] = {'trials': len(subset), 'false_accepts': sum(r['accepted'] for r in subset),
                            'false_acceptance_rate': ratio(sum(r['accepted'] for r in subset), len(subset))}
    return result


def run(bundle: Path, output: Path) -> dict:
    manifest = json.loads((bundle/'manifest.json').read_text())
    validate(manifest)
    base = load_config()
    reports, all_rows, failed_profiles = [], [], []
    with tempfile.TemporaryDirectory(prefix='sonara-torgo-') as temporary:
        for profile in manifest['profiles']:
            speaker = profile['speaker']
            cfg = Config(raw={'audio': {'sample_rate': 16000}, 'recognition': {'profile_dir': str(Path(temporary)/speaker), 'profile_id': speaker}},
                         intents=[Intent(id=w.upper(), label=w, speak=w, notify=False) for w in WORDS], prompts=base.prompts, root=bundle)
            rec = Recognizer(cfg)
            invalid_enrollment = []
            for entry in profile['references']:
                audio, sr = read_wav(checked_path(bundle, entry))
                if sr != 16000:
                    raise ValueError('expected 16 kHz PCM')
                try:
                    rec.prepare(audio, manual=True)
                    seq = rec.embed(audio, manual=True)
                    if seq is None:
                        raise ValueError('feature extraction failed')
                    rec.clf.add(entry['label'], seq)
                except ValueError as exc:
                    invalid_enrollment.append({'source': entry['file'], 'reason': str(exc)})
            if invalid_enrollment:
                failed_profiles.append({'speaker': speaker, 'invalid_enrollment': invalid_enrollment,
                                        'queries_not_run': len(profile['queries'])})
                print(f'{speaker}: enrollment failed; no partial profile evaluated', flush=True)
                continue
            rec.clf.calibrate()  # Enrollment-only LOO and cross-intent negatives.
            rec.clf.profile_id = speaker
            rec.clf.save(profile_path(cfg, speaker))
            rec.reload(speaker)
            if rec.clf.counts() != {w.upper(): 2 for w in WORDS}:
                raise ValueError('profile isolation or enrollment persistence failed')
            rows = []
            for entry in profile['queries']:
                audio, sr = read_wav(checked_path(bundle, entry))
                if sr != 16000:
                    raise ValueError('expected 16 kHz PCM')
                try:
                    rec.prepare(audio, manual=True)
                    valid = True
                except ValueError:
                    valid = False
                prediction = rec.recognize(audio, manual=True)
                row = {'profile': speaker, 'source': entry['file'], 'transcription': entry['transcription'],
                       'truth': entry['label'], 'category': entry['category'], 'valid_audio': valid,
                       'duration_s': len(audio)/sr, **prediction.to_dict()}
                rows.append(row)
                print(f'{speaker} {entry["file"]}: {entry["label"]} -> {prediction.intent or "UNKNOWN"}', flush=True)
            reports.append({'speaker': speaker, 'calibration': rec.clf.calibration, **metrics(rows), 'rows': rows})
            all_rows.extend(rows)
    report = {'repository': REPOSITORY, 'revision': REVISION, 'words': list(WORDS),
              'protocol': manifest['protocol'], 'warning': manifest['warning'],
              'platform': platform.platform(), 'machine': platform.machine(),
              'enrollment_per_word': 2, 'planned_speakers': list(SPEAKERS),
              'failed_profiles': failed_profiles, 'profiles': reports, 'aggregate': metrics(all_rows),
              'peak_process_rss_mib': peak_process_rss_mib(), 'manifest_sha256': hashlib.sha256((bundle/'manifest.json').read_bytes()).hexdigest()}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False))
    print(json.dumps(report['aggregate'], indent=2), flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'evaluate'])
    parser.add_argument('--directory', type=Path, default=Path('data/evaluation/torgo'))
    parser.add_argument('--output', type=Path, default=Path('roles/speech/docs/validation/torgo_laptop.json'))
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare(args.directory)
    else:
        run(args.directory/'bundle', args.output)


if __name__ == '__main__':
    main()
