"""Stream a bounded real-speech diagnostic bundle; never invent repeated enrollments.

Optional laptop dependencies: pip install '.[corpus-eval]'
The board receives only bounded PCM WAVs and a manifest, not Datasets/Torch or the full corpus.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import unicodedata
import urllib.request
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from sonara.audio.vad import trim_silence
from sonara.audio.wavio import write_wav
from sonara.config import load_config
from sonara.recognizer import Recognizer

REPOSITORY = "B-Czarnetzki/dysarthric_german"


def normalize_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def bounded_audio(audio: np.ndarray, sr: int, allow_window: bool) -> tuple[np.ndarray, dict]:
    """Trim endpoints conservatively; never crop an enrollment phrase to fit.

    UNKNOWN stress inputs may use one explicitly labeled five-second window per source.
    """
    if sr != 16000:
        raise ValueError("convert corpus to 16 kHz before segmentation")
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim != 1 or not 0 < len(audio) <= sr*120 or not np.isfinite(audio).all():
        raise ValueError("invalid or oversized corpus recording")
    # Match the runtime's DC removal before endpoint energy analysis.
    centered = audio - audio.mean()
    trimmed = trim_silence(centered, sr)
    if len(trimmed) < .3*sr:
        raise ValueError("too little speech")
    offset = (trimmed.ctypes.data - centered.ctypes.data) // centered.itemsize
    complete = len(trimmed) <= 5*sr
    if not complete and not allow_window:
        raise ValueError("complete vocalization exceeds five seconds")
    clip = trimmed[:5*sr].copy()
    return clip, {"original_duration_s": len(audio)/sr, "start_s": offset/sr,
                  "end_s": (offset+len(clip))/sr,
                  "kind": "complete_utterance" if complete else "five_second_unknown_window"}


def pcm_hash(audio: np.ndarray) -> str:
    return hashlib.sha256(np.round(np.asarray(audio)*32768).astype('<i4').tobytes()).hexdigest()


def prepare(output: Path, candidates: int = 64, queries: int = 40, references: int = 5) -> dict:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault('HF_HOME', str(output/'hf_home'))
    from datasets import Audio, load_dataset
    import soundfile as sf
    from scipy.signal import resample_poly
    from math import gcd

    metadata_path = output/'hub.json'
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text())
    else:
        with urllib.request.urlopen(f'https://huggingface.co/api/datasets/{REPOSITORY}', timeout=60) as response:
            metadata = json.load(response)
        metadata_path.write_text(json.dumps(metadata, indent=2))
    revision = metadata['sha']
    common = {'revision': revision, 'streaming': True, 'cache_dir': str(output/'hf_cache'), 'token': False}
    text_path = output/'transcripts.json'
    if text_path.exists():
        transcripts = json.loads(text_path.read_text())
    else:
        transcripts = []
        for split in ('train', 'test'):
            dataset = load_dataset(REPOSITORY, split=split, columns=['path', 'text'], **common)
            transcripts.extend({'split': split, 'row_index': i, **row} for i, row in enumerate(dataset))
        text_path.write_text(json.dumps(transcripts, indent=2))
    counts = Counter(normalize_text(row['text']) for row in transcripts)
    schema = [feature['name'] for feature in metadata['cardData']['dataset_info']['features']]
    audit = {'repository': REPOSITORY, 'revision': revision, 'rows': len(transcripts),
             'unique_transcripts': len(counts), 'transcript_repetition_histogram': dict(Counter(counts.values())),
             'speaker_id_available': any(k in schema for k in ('speaker', 'speaker_id', 'patient_id')),
             'license_declared': metadata.get('cardData', {}).get('license'),
             'supports_five_enrollment_three_heldout': any(n >= 8 for n in counts.values())}
    (output/'audit.json').write_text(json.dumps(audit, indent=2))
    print(json.dumps(audit), flush=True)

    raw = output/'raw'
    raw.mkdir(exist_ok=True)
    bundle = output/'bundle'
    bundle.mkdir(exist_ok=True)
    rec_cfg = load_config()
    rec_cfg.raw['recognition']['profile_dir'] = str(output/'unused_profiles')
    rec = Recognizer(rec_cfg)

    def decode(row):
        name = Path(row['path']).name
        cached = raw/name
        if not cached.exists():
            data = row['audio']['bytes']
            if data is None:
                raise ValueError('expected embedded corpus audio bytes')
            cached.write_bytes(data)
        data = cached.read_bytes()
        info = sf.info(io.BytesIO(data))
        if not 0 < info.duration <= 120:
            raise ValueError('corpus audio duration outside safety bound')
        samples, sr = sf.read(io.BytesIO(data), dtype='float32', always_2d=True)
        samples = samples.mean(axis=1)
        source_digest = pcm_hash(samples)
        if sr != 16000:
            divisor = gcd(sr,16000)
            samples = resample_poly(samples,16000//divisor,sr//divisor).astype(np.float32)
        return samples, source_digest

    selected = sorted((r for r in transcripts if r['split']=='train'),
                      key=lambda row: (len(row['text']),row['path']))[:candidates]
    # Cache only selected raw examples; server-side Parquet column/filter pushdown is supported.
    missing = [r['path'] for r in selected if not (raw/Path(r['path']).name).exists()]
    if missing:
        dataset = load_dataset(REPOSITORY, split='train', filters=[('path','in',missing)], **common)
        dataset = dataset.cast_column('audio',Audio(decode=False))
        for row in dataset:
            decode(row)
            print(f"cached train {Path(row['path']).name}",flush=True)
    refs, skipped = [], []
    for row in selected:
        try:
            samples, digest = decode(row)
            clip, segmentation = bounded_audio(samples,16000,False)
            rec.prepare(clip,manual=True)
        except (ValueError, OSError) as exc:
            skipped.append({'source':Path(row['path']).name,'reason':str(exc)})
            continue
        if any(r['source_pcm_sha256']==digest or normalize_text(r['text'])==normalize_text(row['text']) for r in refs):
            continue
        label = f'PHRASE_{len(refs)+1:02d}'
        relative = f'references/{label}.wav'
        write_wav(bundle/relative,clip,16000)
        refs.append({'label':label,'file':relative,'text':row['text'],'split':'train',
                     'source':Path(row['path']).name,'source_pcm_sha256':digest,**segmentation})
        if len(refs)==references:
            break
    if len(refs)<2:
        raise ValueError(f'only {len(refs)} complete 0.3–5 second references found; no useful multi-phrase diagnostic')
    ref_digests = {r['source_pcm_sha256'] for r in refs}
    ref_texts = {normalize_text(r['text']) for r in refs}
    tests, seen = [], set(ref_digests)
    dataset = load_dataset(REPOSITORY, split='test', **common).cast_column('audio',Audio(decode=False))
    for row_index,row in enumerate(dataset):
        # Use the first N official test rows regardless of matching score or audio quality.
        if row_index>=queries:
            break
        try:
            samples, digest = decode(row)
            if digest in seen or normalize_text(row['text']) in ref_texts:
                skipped.append({'source':Path(row['path']).name,'reason':'duplicate source or enrolled transcript'})
                continue
            seen.add(digest)
            clip, segmentation = bounded_audio(samples,16000,True)
            relative = f'queries/{row_index:04d}.wav'
            write_wav(bundle/relative,clip,16000)
            tests.append({'file':relative,'split':'test','row_index':row_index,
                          'source':Path(row['path']).name,'source_pcm_sha256':digest,**segmentation})
        except (ValueError,OSError) as exc:
            skipped.append({'source':Path(row['path']).name,'reason':str(exc)})
    manifest = {'version':1,'audit':audit,'protocol':'single-template real-speech rejection/latency diagnostic',
                'held_out_known_accuracy_available':False,'speaker_dependent_validation':False,
                'manual_boundaries':True,'references':refs,'queries':tests,'skipped':skipped,
                'selection':{'train_candidates':candidates,'reference_rule':'shortest transcript then source path; first complete valid utterances',
                             'official_test_rows_considered':queries,'unknown_rule':'first official test rows; one complete utterance or first 5s voiced-span window per source'},
                'warning':'One example per phrase, undocumented speakers, no independent repeated positives. Not Sonara intent accuracy or clinical validation.'}
    for entry in refs+tests:
        entry['wav_sha256']=hashlib.sha256((bundle/entry['file']).read_bytes()).hexdigest()
    (bundle/'manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False))
    print(f'Prepared {len(refs)} whole reference utterances and {len(tests)} independent UNKNOWN sources in {bundle}',flush=True)
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('data/evaluation/dysarthric_german'))
    parser.add_argument('--candidates',type=int,default=64)
    parser.add_argument('--queries',type=int,default=40)
    parser.add_argument('--references',type=int,default=5)
    args=parser.parse_args()
    if not 2<=args.references<=10 or not args.references<=args.candidates<=200 or not 1<=args.queries<=125:
        parser.error('references: 2–10; candidates: references–200; queries: 1–125')
    prepare(args.output,args.candidates,args.queries,args.references)


if __name__=='__main__':
    main()
