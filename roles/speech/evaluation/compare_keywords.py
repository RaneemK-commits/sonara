"""Exploratory keyword-in-context comparison, using the existing TORGO bundle.

Streams are artificial compositions of REAL held-out word recordings and other
words, not natural coarticulated phrases. This reuses an already inspected test
set; it is development evidence, not a fresh final accuracy estimate.
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
from sonara.models.classifier import PrototypeClassifier
from sonara.models.features import FeatureConfig, mfcc
from sonara.models.keywords import KeywordSpotter
from roles.speech.evaluation.evaluate_real_corpus import checked_path
from roles.speech.evaluation.memory import peak_process_rss_mib
from roles.speech.evaluation.torgo import validate


def overlap(a: tuple[float,float], b: tuple[float,float]) -> float:
    intersection=max(0.,min(a[1],b[1])-max(a[0],b[0]))
    union=max(a[1],b[1])-min(a[0],b[0])
    return intersection/union if union>0 else 0.


def summarize(rows: list[dict], key: str) -> dict:
    known=[r for r in rows if r['category']=='known']
    negatives=[r for r in rows if r['category']!='known']
    correct=best=0
    false=0
    latencies=[]
    for row in rows:
        events=row[key]['events']
        def located(e):
            return (row['category']=='known' and e['best']==row['truth']
                    and overlap((e['start_s'],e['end_s']),tuple(row['truth_interval']))>=.3)
        best+=any(located(e) for e in events)
        correct+=any(located(e) and e['accepted'] and e['intent']==row['truth'] for e in events)
        false+=sum(e['accepted'] and not (located(e) and e['intent']==row['truth']) for e in events)
        latencies.append(row[key]['processing_ms'])
    return {'known_trials':len(known),'negative_trials':len(negatives),
            'correct_localized_accepts':correct,'correct_localized_accept_rate':correct/len(known) if known else None,
            'localized_best_label_before_rejection':best,
            'false_accepted_events':false,
            'negative_trials_with_accepts':sum(any(e['accepted'] for e in r[key]['events']) for r in negatives),
            'processing_ms_mean':float(np.mean(latencies)) if latencies else None,
            'processing_ms_p95':float(np.percentile(latencies,95)) if latencies else None,
            'real_time_factor':sum(latencies)/1000/sum(r['duration_s'] for r in rows) if rows else None}


def run(bundle: Path, output: Path, stream: bool=False) -> dict:
    manifest=json.loads((bundle/'manifest.json').read_text())
    validate(manifest)
    rows,failed=[],[]
    for profile in manifest['profiles']:
        def load(entry):
            audio,sr=read_wav(checked_path(bundle,entry))
            if sr!=16000:raise ValueError('16 kHz bundle required')
            return audio
        recordings={}
        try:
            for entry in profile['references']:
                clip=KeywordSpotter.audio(load(entry))
                recordings.setdefault(entry['label'],[]).append(clip)
            model=KeywordSpotter.enroll(recordings,trim_endpoints=False,allow_few_shot=True,alignment_stride=1,feature_weights=(1.,1.,1.),stride_s=.5,max_candidates=3,refine_boundaries=False)  # bundle is already endpoint-trimmed
        except ValueError as exc:
            failed.append({'speaker':profile['speaker'],'reason':str(exc)})
            continue
        baseline=PrototypeClassifier()
        for label,clips in recordings.items():
            for clip in clips:baseline.add(label,mfcc(clip))
        baseline.calibrate()
        unknown=[e for e in profile['queries'] if e['category']=='unknown']
        # First held-out take per keyword; first five unknowns and five impostors.
        seen=set();selected=[]
        for entry in profile['queries']:
            if entry['category']=='known' and entry['label'] not in seen:
                selected.append(entry);seen.add(entry['label'])
        for category in ('unknown','impostor'):
            selected.extend([e for e in profile['queries'] if e['category']==category][:5])
        for index,entry in enumerate(selected):
            clip=load(entry)
            target=entry['category']=='known'
            if target:
                # No artificial silence inserted; use central speech-bearing context from
                # two other-word recordings. Join artifacts remain a corpus limitation.
                budget=min(8000,(80000-len(clip))//2)
                if budget<1600:
                    failed.append({'speaker':profile['speaker'],'source':entry['file'],
                                   'reason':'insufficient context budget in bounded five-second window'})
                    continue
                def context(source):
                    a=load(source)
                    width=min(len(a),budget)
                    start=max(0,(len(a)-width)//2)
                    return a[start:start+width]
                before=context(unknown[index%len(unknown)])
                after=context(unknown[(index+1)%len(unknown)])
                phrase=np.concatenate([before,clip,after]).astype(np.float32)
                truth_interval=[len(before)/16000,(len(before)+len(clip))/16000]
                sources=[unknown[index%len(unknown)]['file'],entry['file'],unknown[(index+1)%len(unknown)]['file']]
            else:
                phrase=clip
                truth_interval=None
                sources=[entry['file']]
            row={'speaker':profile['speaker'],'source_files':sources,'category':entry['category'],
                 'truth':entry['label'],'truth_interval':truth_interval,'duration_s':len(phrase)/16000}
            # Whole-utterance baseline has no keyword localization: report its intent
            # accuracy separately instead of assigning the entire phrase a keyword interval.
            for name,classifier,features in (
                    ('utterance_cmvn',baseline,mfcc(KeywordSpotter.audio(phrase))),
                    ('shared_scaling_whole',model.classifier,
                     model.normalize(mfcc(KeywordSpotter.audio(phrase),config=model.feature_config)))):
                start=time.perf_counter();prediction=classifier.predict(features)
                row[name]={'matching_ms':(time.perf_counter()-start)*1000,**prediction.to_dict()}
            start=time.perf_counter();events=model.scan(phrase)
            row['subsequence']={'processing_ms':(time.perf_counter()-start)*1000,'events':[e.to_dict() for e in events]}
            if stream:
                model.reset();events=[];start=time.perf_counter()
                for i in range(0,len(phrase),800):events.extend(model.feed(phrase[i:i+800]))
                row['stream']={'processing_ms':(time.perf_counter()-start)*1000,'events':[e.to_dict() for e in events]}
            rows.append(row)
            print(f"{profile['speaker']} {entry['category']} {entry['label']}: "
                  f"utterance={row['utterance_cmvn']['intent']} keyword={[e.prediction.intent for e in events]}",flush=True)
    summary={name:summarize(rows,name) for name in (('subsequence','stream') if stream else ('subsequence',))}
    for name in ('utterance_cmvn','shared_scaling_whole'):
        known=[r for r in rows if r['category']=='known'];negative=[r for r in rows if r['category']!='known']
        summary[name]={'known_trials':len(known),
                       'correct_intent_accepts':sum(r[name]['intent']==r['truth'] for r in known),
                       'best_label_correct_before_rejection':sum(r[name]['best']==r['truth'] for r in known),
                       'negative_trials_with_accepts':sum(r[name]['accepted'] for r in negative)}
    report={'source_repository':manifest['repository'],'source_revision':manifest['revision'],
            'words':manifest['words'],'platform':platform.platform(),'machine':platform.machine(),
            'python':platform.python_version(),'numpy':np.__version__,
            'keyword_settings':{'max_candidates':3,'stride_s':.5,'window_s':5.,
                                'duration_ratio':[.5,2.],'step_penalty':.05,'hop_ms':10},
            'protocol':'First held-out take per word; central <=0.5 s unknown context on each side; 5 unknown + 5 impostor trials per completed profile.',
            'artificially_composed_streams':True,'natural_phrase_accuracy_available':False,
            'fresh_test_set':False,'threshold_tuned_on_queries':False,
            'normalization':'pooled mean/variance from enrollment only; reused unchanged for every stream window',
            'peak_process_rss_mib':peak_process_rss_mib(),'summary':summary,'failed':failed,'rows':rows,
            'warning':'Exploratory development comparison. Not WATER/PAIN accuracy, natural phrase or patient validation. Do not connect to caregiver dispatch.'}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps(summary,indent=2))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,default=Path('data/evaluation/torgo/bundle'))
    parser.add_argument('--output',type=Path,default=Path('roles/speech/docs/validation/keyword_comparison_laptop.json'))
    parser.add_argument('--stream',action='store_true',help='also replay 50 ms chunks through rolling streaming buffers')
    args=parser.parse_args()
    run(args.bundle,args.output,args.stream)
