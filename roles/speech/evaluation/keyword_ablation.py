"""Compare faster matching, feature weighting and explicitly synthetic enrollment.

All synthetic training variants descend ONLY from enrollment sources. Independent
TORGO test takes and extra filler remain outside fitting/calibration. The corpus
is already a development set; variants do not create more human recordings.
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
from sonara.models.keywords import KeywordSpotter
from roles.speech.evaluation.evaluate_real_corpus import checked_path
from roles.speech.evaluation.evaluate_keyword_streams import event_metrics
from roles.speech.evaluation.memory import peak_process_rss_mib

VARIANTS={
    'balanced_30ms':{'alignment_stride':3,'stride_s':.75,'feature_weights':(1.,.5,.25),'synthetic_per_intent':0},
    'economy_40ms':{'alignment_stride':4,'stride_s':.75,'feature_weights':(1.,.5,.25),'synthetic_per_intent':0},
    'augmented_40ms':{'alignment_stride':4,'stride_s':.75,'feature_weights':(1.,.5,.25),'synthetic_per_intent':3,'augmentation_policy':'balanced20'},
    'fast_20ms':{'alignment_stride':2,'stride_s':.5,'feature_weights':(1.,1.,1.),'synthetic_per_intent':0},
    'weighted_20ms':{'alignment_stride':2,'stride_s':.5,'feature_weights':(1.,.5,.25),'synthetic_per_intent':0},
    'augmented_20ms':{'alignment_stride':2,'stride_s':.5,'feature_weights':(1.,.5,.25),'synthetic_per_intent':3,'augmentation_policy':'mild35'},
    'noise_augmented_20ms':{'alignment_stride':2,'stride_s':.5,'feature_weights':(1.,.5,.25),'synthetic_per_intent':3,'augmentation_policy':'balanced20'},
}

# Freeze earlier ablation protocols; new refinement/cache is an explicit new arm.
for settings in VARIANTS.values():
    settings['max_candidates']=3
    settings['refine_boundaries']=False
VARIANTS['refined_30ms']={'alignment_stride':3,'stride_s':.75,'max_candidates':2,
    'feature_weights':(1.,.5,.25),'synthetic_per_intent':0,'refine_boundaries':True}
VARIANTS['refined_augmented_40ms']={'alignment_stride':4,'stride_s':.75,'max_candidates':2,
    'feature_weights':(1.,.5,.25),'synthetic_per_intent':3,'augmentation_policy':'balanced20','refine_boundaries':True}

VARIANTS['paced_30ms']={**VARIANTS['refined_30ms'],'stride_s':1.25}


def recordings(directory: Path, speaker: str) -> dict[str,list[np.ndarray]]:
    sources=json.loads((directory/'bundle/manifest.json').read_text())
    profile=next(p for p in sources['profiles'] if p['speaker']==speaker)
    result={}
    for entry in profile['references']:
        audio,sr=read_wav(checked_path(directory/'bundle',entry))
        if sr!=16000:raise ValueError('16 kHz required')
        result.setdefault(entry['label'],[]).append(audio)
    return result


def summarize(rows: list[dict]) -> dict:
    duration=sum(r['audio_duration_s'] for r in rows)
    count=sum(r['truth_events'] for r in rows);correct=sum(r['correct_events'] for r in rows)
    false=sum(r['false_accepted_events'] for r in rows)
    return {'streams':len(rows),'audio_duration_s':duration,'target_occurrences':count,
            'correct_events':correct,'event_recall':correct/count if count else None,
            'false_accepted_events':false,'precision':correct/(correct+false) if correct+false else None,
            'false_accepted_events_per_hour':false*3600/duration if duration else None,
            'real_time_factor':sum(r['processing_s'] for r in rows)/duration if duration else None}


def run(directory: Path, output: Path, variants: list[str], limit: int | None=None) -> dict:
    manifest=json.loads((directory/'streams.json').read_text())
    streams=manifest['streams'][:limit] if limit is not None else manifest['streams']
    report={'platform':platform.platform(),'machine':platform.machine(),'python':platform.python_version(),
            'numpy':np.__version__,'source_revision':manifest['source_revision'],
            'independent_target_sources':manifest['independent_positive_source_count'],
            'synthetic_data_is_independent':False,'heldout_threshold_tuning':False,
            'variants':{},'warning':'Development comparison on artificial streams, not natural WATER/PAIN accuracy. Corpus profiles have two real takes per keyword regardless of synthetic count.'}
    for name in variants:
        options=VARIANTS[name];models={};rows=[];calibration={}
        for stream in streams:
            speaker=stream['speaker']
            if speaker not in models:
                model=KeywordSpotter.enroll(recordings(directory,speaker),trim_endpoints=False,
                                             allow_few_shot=True,seed=412,**options)
                models[speaker]=model;calibration[speaker]=model.classifier.calibration
                model.save(directory/'ablation_profiles'/name/speaker)
            model=models[speaker];model.reset()
            audio,sr=read_wav(checked_path(directory,stream),max_seconds=60)
            if sr!=16000:raise ValueError('16 kHz required')
            events=[];scan_ms=[];started=time.perf_counter()
            for i in range(0,len(audio),800):
                before=time.perf_counter();found=model.feed(audio[i:i+800]);elapsed=(time.perf_counter()-before)*1000
                if found:scan_ms.append(elapsed)
                events.extend(e.to_dict() for e in found)
            elapsed=time.perf_counter()-started
            stats=event_metrics(stream['events'],events,len(audio)/16000)
            rows.append({'speaker':speaker,'base_id':stream['base_id'],'condition':stream['condition'],
                         'processing_s':elapsed,**stats,
                         'scan_ms_p95':float(np.percentile(scan_ms,95)) if scan_ms else None})
            print(f'{name} {speaker}/{stream["base_id"]}/{stream["condition"]}: '
                  f'{stats["correct_events"]}/{stats["truth_events"]} correct, {stats["false_accepted_events"]} false',flush=True)
        conditions={c:summarize([r for r in rows if r['condition']==c]) for c in sorted({r['condition'] for r in rows})}
        report['variants'][name]={'settings':options,'calibration':calibration,'summary':summarize(rows),
                                  'by_condition':conditions,'rows':rows}
        report['peak_process_rss_mib']=peak_process_rss_mib()
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,indent=2,allow_nan=False))
        print(json.dumps(report['variants'][name]['summary'],indent=2),flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,default=Path('data/evaluation/torgo_noisy'))
    parser.add_argument('--output',type=Path,default=Path('roles/speech/docs/validation/keyword_ablation_laptop.json'))
    parser.add_argument('--variants',nargs='+',choices=list(VARIANTS),default=list(VARIANTS))
    parser.add_argument('--limit',type=int)
    args=parser.parse_args()
    if args.limit is not None and not 1<=args.limit<=115:parser.error('limit must be 1–115')
    run(args.directory,args.output,args.variants,args.limit)
