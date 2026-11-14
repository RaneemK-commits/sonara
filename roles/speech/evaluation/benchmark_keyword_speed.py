"""Paired bounded-stream timing: exact batching, coarse matching and augmentation.

Dataset streams and template waves are public corpus fixtures only. No live mic,
TTS, active profile or caregiver API access. Timing excludes profile construction.
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from sonara.audio.wavio import read_wav
from sonara.models import keywords as keyword_module
from sonara.models.keywords import KeywordSpotter
from sonara.models.subsequence import subsequence_candidates,subsequence_candidates_many
from roles.speech.evaluation.keyword_ablation import recordings
from roles.speech.evaluation.evaluate_real_corpus import checked_path
from roles.speech.evaluation.memory import peak_process_rss_mib


def scalar(templates,stream,**kwargs):
    return [subsequence_candidates(template,stream,**kwargs) for template in templates]


def replay(model,audio,matcher):
    old=keyword_module.subsequence_candidates_many
    keyword_module.subsequence_candidates_many=matcher
    model.reset();events=[];scans=[]
    try:
        start=time.perf_counter()
        for i in range(0,len(audio),800):
            tick=time.perf_counter();found=model.feed(audio[i:i+800]);elapsed=(time.perf_counter()-tick)*1000
            if found:scans.append(elapsed)
            events.extend(e.to_dict() for e in found)
        return time.perf_counter()-start,events,scans
    finally:keyword_module.subsequence_candidates_many=old


def run(directory: Path,output: Path,runs: int=2,methods: list[str] | None=None) -> dict:
    manifest=json.loads((directory/'streams.json').read_text())
    selected=[s for s in manifest['streams'] if (s['speaker'],s['base_id'],s['condition']) in
              [('F03','target_02','clean'),('M02','target_00','background_20db')]]
    report={'platform':platform.platform(),'machine':platform.machine(),'python':platform.python_version(),
            'numpy':np.__version__,'runs':runs,'cases':[],
            'note':'Whole-stream processing excludes profile fitting/capture/TTS. Scan timing distributions cover calls returning proposals, not empty scans; all feed work is included in total processing and real-time factor. Shared machine.'}
    for stream in selected:
        clips=recordings(directory,stream['speaker'])
        common={'trim_endpoints':False,'allow_few_shot':True,'seed':412,
                'feature_weights':(1.,.5,.25),'max_candidates':3,'refine_boundaries':False}
        settings={
            'scalar_10ms':{'alignment_stride':1,'stride_s':.5,'feature_weights':(1,1,1)},
            'batched_10ms':{'alignment_stride':1,'stride_s':.5,'feature_weights':(1,1,1)},
            'fast_weighted_20ms':{'alignment_stride':2,'stride_s':.5},
            'augmented_20ms':{'alignment_stride':2,'stride_s':.5,'synthetic_per_intent':3,'augmentation_policy':'mild35'},
            'balanced_30ms':{'alignment_stride':3,'stride_s':.75},
            'economy_40ms':{'alignment_stride':4,'stride_s':.75},
            'augmented_40ms':{'alignment_stride':4,'stride_s':.75,'synthetic_per_intent':3},
            'paced_30ms':{'alignment_stride':3,'stride_s':1.25,'max_candidates':2,'refine_boundaries':True},
            'paced_augmented_40ms':{'alignment_stride':4,'stride_s':1.25,'synthetic_per_intent':3,'max_candidates':2,'refine_boundaries':True},
            'refined_30ms':{'alignment_stride':3,'stride_s':.75,'max_candidates':2,'refine_boundaries':True},
            'refined_augmented_40ms':{'alignment_stride':4,'stride_s':.75,'synthetic_per_intent':3,
                                      'max_candidates':2,'refine_boundaries':True},
        }
        requested=methods or ['scalar_10ms','batched_10ms','fast_weighted_20ms','augmented_20ms']
        models={};fitted={}
        for name in requested:
            options={**common,**settings[name]};key=json.dumps(options,sort_keys=True)
            if key not in fitted:fitted[key]=KeywordSpotter.enroll(clips,**options)
            models[name]=(fitted[key],scalar if name=='scalar_10ms' else subsequence_candidates_many)
        audio,sr=read_wav(checked_path(directory,stream),max_seconds=60)
        if sr!=16000:raise ValueError('16 kHz required')
        times={k:[] for k in models};scan_times={k:[] for k in models};signature={}
        # Alternate order to reduce systematic warm-cache/frequency/load bias.
        for repeat in range(runs):
            order=list(models) if repeat%2==0 else list(reversed(models))
            for name in order:
                model,matcher=models[name]
                elapsed,events,scans=replay(model,audio,matcher)
                times[name].append(elapsed);scan_times[name].extend(scans)
                signature[name]=[(e['intent'],e['best'],e['start_s'],e['end_s']) for e in events]
        exact_check='scalar_10ms' in signature and 'batched_10ms' in signature
        if exact_check and signature['scalar_10ms']!=signature['batched_10ms']:
            raise AssertionError('exact batched matcher changed event decisions or timestamps')
        case={'speaker':stream['speaker'],'source':stream['file'],'audio_s':len(audio)/sr,
              'exact_batch_decisions_unchanged':True if exact_check else None,'methods':{}}
        for name,values in times.items():
            case['methods'][name]={'processing_s_mean':float(np.mean(values)),
                'real_time_factor':float(np.mean(values)/(len(audio)/sr)),
                'scan_ms_mean':float(np.mean(scan_times[name])) if scan_times[name] else None,
                'scan_ms_p95':float(np.percentile(scan_times[name],95)) if scan_times[name] else None,
                'template_count':len(models[name][0].classifier.seqs)}
        if 'scalar_10ms' in times and 'fast_weighted_20ms' in times:
            case['fast_vs_scalar_speedup']=float(np.mean(times['scalar_10ms'])/np.mean(times['fast_weighted_20ms']))
        report['cases'].append(case);report['peak_process_rss_mib']=peak_process_rss_mib()
        output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2,allow_nan=False))
        print(json.dumps(case,indent=2),flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,default=Path('data/evaluation/torgo_noisy'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--runs',type=int,default=2)
    parser.add_argument('--methods',nargs='+',choices=['scalar_10ms','batched_10ms','fast_weighted_20ms','augmented_20ms','balanced_30ms','economy_40ms','augmented_40ms','refined_30ms','refined_augmented_40ms','paced_30ms','paced_augmented_40ms'])
    args=parser.parse_args()
    if not 1<=args.runs<=5:parser.error('runs must be 1–5')
    run(args.directory,args.output,args.runs,args.methods)
