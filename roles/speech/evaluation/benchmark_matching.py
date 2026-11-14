"""Paired scalar/batched matching benchmark on an existing local profile and held-out WAV.

No microphone, TTS, controller or running patient profile is changed. Timing covers
matching only; scripts/benchmark.py measures the complete recognition processing path.
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path
from types import MethodType

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from sonara.audio.wavio import read_wav, resample_linear
from sonara.config import load_config
from sonara.models.classifier import PrototypeClassifier
from sonara.models.dtw import dtw_distance
from sonara.recognizer import Recognizer
from roles.speech.evaluation.memory import peak_process_rss_mib


def scalar_scores(self, seq, exclude=None):
    per={}
    for i,(label,template) in enumerate(zip(self.labels,self.seqs)):
        if i!=exclude:
            per.setdefault(label,[]).append(dtw_distance(seq,template,band=self.band))
    return {label:float(np.mean(sorted(values)[:self.k])) for label,values in per.items()}


def run(profile: Path, wav: Path, runs: int, output: Path) -> dict:
    clf=PrototypeClassifier.load(profile)
    cfg=load_config()
    cfg.raw['features']=clf.feature_config.to_dict()
    # Feature extraction needs no loaded patient; keep the caller's selection untouched.
    cfg.raw['recognition']={'profile_dir':str(profile.parent/'unused_benchmark_profiles')}
    rec=Recognizer(cfg)
    audio,sr=read_wav(wav)
    audio=resample_linear(audio,sr,16000)
    seq=rec.embed(audio)
    if seq is None or not clf.seqs:
        raise ValueError('benchmark needs valid speech and enrolled templates')
    baseline=scalar_scores(clf,seq)
    optimized=clf.scores(seq)
    error=max(abs(baseline[label]-optimized[label]) for label in baseline)
    if any(not np.isclose(baseline[label],optimized[label],rtol=1e-10,atol=1e-10) for label in baseline):
        raise AssertionError('batched matching changed scores')
    before=clf.predict(seq).to_dict()
    clf.scores=MethodType(scalar_scores,clf)
    scalar_prediction=clf.predict(seq).to_dict()
    del clf.scores
    if any(before[key]!=scalar_prediction[key] for key in ('intent','accepted','best','distance','margin','threshold','scores')):
        raise AssertionError('batched matching changed the prediction')
    timing={'scalar':[],'batched':[]}
    for i in range(runs):
        order=('scalar','batched') if i%2==0 else ('batched','scalar')
        for method in order:
            start=time.perf_counter()
            scalar_scores(clf,seq) if method=='scalar' else clf.scores(seq)
            timing[method].append((time.perf_counter()-start)*1000)
    def stats(values):
        return {'mean':float(np.mean(values)),'p50':float(np.percentile(values,50)),
                'p95':float(np.percentile(values,95)),'max':max(values)}
    out={'hardware':platform.platform(),'machine':platform.machine(),'python':platform.python_version(),
         'numpy':np.__version__,'audio_s':len(audio)/16000,'frames':len(seq),
         'counts':clf.counts(),'runs':runs,'band':clf.band,
         'matching_ms':{method:stats(values) for method,values in timing.items()},
         'speedup_mean':float(np.mean(timing['scalar'])/np.mean(timing['batched'])),
         'maximum_score_difference':error,'prediction_unchanged':True,
         'peak_process_rss_mib':peak_process_rss_mib(),
         'note':'Paired alternating matching-only timings; no audio capture, feature extraction, network or TTS.'}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(out,indent=2,allow_nan=False))
    print(json.dumps(out,indent=2))
    return out


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',type=Path,required=True)
    parser.add_argument('--wav',type=Path,required=True)
    parser.add_argument('--runs',type=int,default=20)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not 1<=args.runs<=100:
        parser.error('runs must be 1–100')
    try:
        run(args.profile,args.wav,args.runs,args.output)
    except (ValueError,OSError) as exc:
        parser.error(str(exc))
