"""Run an isolated real-speech corpus diagnostic offline, including on the UNO Q.

This is not held-out known-intent accuracy: each reference phrase has only one take.
No controller, microphone, TTS or caregiver endpoint is invoked.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import tempfile
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from sonara.audio.wavio import read_wav
from sonara.config import Config, Intent, load_config
from sonara.recognizer import Recognizer, profile_path
from roles.speech.evaluation.memory import peak_process_rss_mib


def checked_path(bundle: Path, entry: dict) -> Path:
    path=(bundle/entry['file']).resolve()
    if not path.is_relative_to(bundle.resolve()):
        raise ValueError('bundle path escapes its directory')
    if hashlib.sha256(path.read_bytes()).hexdigest()!=entry['wav_sha256']:
        raise ValueError(f'WAV checksum mismatch: {entry["file"]}')
    return path


def validate_manifest(manifest: dict) -> None:
    refs,queries=manifest['references'],manifest['queries']
    if not 2<=len(refs)<=10 or not 1<=len(queries)<=125:
        raise ValueError('expected 2–10 reference phrases and 1–125 queries')
    if len({r['label'] for r in refs})!=len(refs):
        raise ValueError('each reference must represent a distinct phrase')
    sources={r['source_pcm_sha256'] for r in refs}
    if len(sources)!=len(refs) or any(r['split']!='train' or r['kind']!='complete_utterance' for r in refs):
        raise ValueError('references must be distinct complete training utterances')
    names={r['source'] for r in refs}
    waves={r['wav_sha256'] for r in refs}
    for entry in queries:
        if entry['split']!='test' or entry['source_pcm_sha256'] in sources or entry['source'] in names or entry['wav_sha256'] in waves:
            raise ValueError('source recording reused across enrollment/test or test rows')
        sources.add(entry['source_pcm_sha256'])
        names.add(entry['source'])
        waves.add(entry['wav_sha256'])


def run(bundle: Path, output: Path, band: float=.2) -> dict:
    bundle=bundle.resolve()
    manifest=json.loads((bundle/'manifest.json').read_text())
    validate_manifest(manifest)
    base=load_config()
    with tempfile.TemporaryDirectory(prefix='sonara-real-corpus-') as temporary:
        cfg=Config(raw={'audio':{'sample_rate':16000},'recognition':{'profile_dir':temporary,'profile_id':'corpus_only','band':band,'margin':.12}},
                   intents=[Intent(id=r['label'],label=r['label'],speak=r['text'],notify=False) for r in manifest['references']],
                   prompts=base.prompts,root=bundle)
        rec=Recognizer(cfg)
        reference_audio={}
        for entry in manifest['references']:
            audio,sr=read_wav(checked_path(bundle,entry))
            if sr!=16000:
                raise ValueError('portable bundle must use 16 kHz PCM WAV')
            seq=rec.embed(audio,manual=True)
            if seq is None:
                raise ValueError(f'invalid reference: {entry["file"]}')
            rec.clf.add(entry['label'],seq)
            reference_audio[entry['label']]=audio
        rec.clf.calibrate()
        rec.clf.profile_id='corpus_only'
        rec.clf.save(profile_path(cfg,'corpus_only'))
        rec.reload('corpus_only')
        calibration=rec.clf.calibration
        sanity=[]
        for label,audio in reference_audio.items():
            prediction=rec.recognize(audio,manual=True)
            sanity.append({'reference':label,'is_enrollment_recording':True,**prediction.to_dict()})
        rows=[]
        for entry in manifest['queries']:
            audio,sr=read_wav(checked_path(bundle,entry))
            if sr!=16000:
                raise ValueError('query sampling rate must be 16 kHz')
            try:
                _,quality=rec.prepare(audio,manual=True)
                valid=True
            except ValueError as exc:
                quality={'error':str(exc)}
                valid=False
            prediction=rec.recognize(audio,manual=True)
            rows.append({'source':entry['source'],'kind':entry['kind'],'audio_s':len(audio)/sr,
                         'truth':'UNKNOWN','valid_audio':valid,'quality':quality,**prediction.to_dict()})
            print(f'{entry["source"]}: {prediction.intent or "UNKNOWN"}, {prediction.latency_ms:.1f} ms',flush=True)
        valid=[r for r in rows if r['valid_audio']]
        accepted=sum(r['accepted'] for r in valid)
        times=[r['latency_ms'] for r in valid]
        def stats(values):
            return {'mean':float(np.mean(values)),'p50':float(np.percentile(values,50)),
                    'p95':float(np.percentile(values,95)),'max':max(values)} if values else None
        per_kind={}
        for kind in sorted({r['kind'] for r in rows}):
            subset=[r for r in valid if r['kind']==kind]
            n=len(subset)
            per_kind[kind]={'valid_unknown_count':n,'accepted':sum(r['accepted'] for r in subset),
                            'false_accept_rate':sum(r['accepted'] for r in subset)/n if n else None,
                            'latency_ms':stats([r['latency_ms'] for r in subset])}
        report={'repository':manifest['audit']['repository'],'revision':manifest['audit']['revision'],
                'protocol':manifest['protocol'],'hardware':platform.platform(),'machine':platform.machine(),
                'python':platform.python_version(),'numpy':np.__version__,
                'reference_count':len(reference_audio),'takes_per_phrase':1,'band':band,
                'held_out_known_accuracy':None,'speaker_dependent_validation':False,
                'warning':manifest['warning'],'audit':manifest['audit'],'selection':manifest['selection'],
                'calibration':calibration,'enrollment_self_match_sanity':sanity,
                'unknown':{'total_sources':len(rows),'valid_audio_count':len(valid),'invalid_audio_count':len(rows)-len(valid),
                           'false_accept_count':accepted,'false_accept_rate':accepted/len(valid) if valid else None,
                           'rejection_rate':1-accepted/len(valid) if valid else None,
                           'confusion':dict(Counter(r['intent'] or 'UNKNOWN' for r in valid))},
                'per_input_kind':per_kind,'processing_latency_ms':stats(times),
                'peak_process_rss_mib':peak_process_rss_mib(),
                'template_mib':sum(s.nbytes for s in rec.clf.seqs)/1024**2,'rows':rows,
                'isolated_from_running_service':True,'caregiver_requests_created':0}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps({k:v for k,v in report.items() if k not in ('rows','calibration','enrollment_self_match_sanity')},indent=2))
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--band',type=float,default=.2)
    args=parser.parse_args()
    if not 0<=args.band<=1:
        parser.error('band must be in [0,1]')
    try:
        run(args.bundle,args.output,args.band)
    except (ValueError,KeyError,OSError) as exc:
        parser.error(str(exc))


if __name__=='__main__':
    main()
