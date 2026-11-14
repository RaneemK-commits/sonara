"""Seen-source synthetic robustness demo; NEVER independent recognition accuracy.

The test keyword is a perturbed enrollment recording. This answers whether the
software tolerates small changes around a known sound, not whether it generalizes
to a new human utterance. Kept separate from the independent-source ablation.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from sonara.audio.wavio import read_wav,write_wav
from sonara.models.keywords import KeywordSpotter
from roles.speech.evaluation.keyword_ablation import recordings
from roles.speech.evaluation.noisy_streams import compose,add_noise,preview
from roles.speech.evaluation.evaluate_real_corpus import checked_path
from roles.speech.evaluation.evaluate_keyword_streams import event_metrics


def run(directory: Path,output_dir: Path,report_path: Path,policy: str='mild35') -> dict:
    manifest=json.loads((directory/'bundle/manifest.json').read_text())
    results=[];listening=[]
    for profile in manifest['profiles']:
        speaker=profile['speaker']
        if speaker not in ('F03','M02','M03'):continue
        model=KeywordSpotter.enroll(recordings(directory,speaker),trim_endpoints=False,
                                     allow_few_shot=True,synthetic_per_intent=3,seed=412,augmentation_policy=policy,alignment_stride=2,stride_s=.5,max_candidates=3,refine_boundaries=False)
        fillers=[r for r in profile['queries'] if r.get('additional_filler')]
        first={}
        for entry in profile['references']:first.setdefault(entry['label'],entry)
        for i,(label,parent) in enumerate(first.items()):
            audio,sr=read_wav(checked_path(directory/'bundle',parent))
            # New mild perturbation parameters, but still the SAME real source family.
            size=round(len(audio)/1.02)
            if size<4800:size=len(audio)
            target=(.92*np.interp(np.linspace(0,len(audio)-1,size),np.arange(len(audio)),audio)).astype(np.float32)
            context=[fillers[(i*2+j)%len(fillers)] for j in range(2)]
            parts=[]
            for e in context:
                a,s=read_wav(checked_path(directory/'bundle',e));parts.append((a,e))
            parts.insert(1,(target,{**parent,'target':True}))
            clean,truth,segments,mask=compose(parts,71+i)
            for condition in ('clean','gap_noise','background_20db','background_10db'):
                mixed,noise=add_noise(clean,mask,condition,772+i)
                relative=f'{speaker}/{label}_{condition}.wav'
                write_wav(output_dir/relative,mixed,16000)
                model.reset();events=[]
                for start in range(0,len(mixed),800):events.extend(e.to_dict() for e in model.feed(mixed[start:start+800]))
                stats=event_metrics(truth,events,len(mixed)/16000)
                results.append({'speaker':speaker,'label':label,'condition':condition,'seen_parent':parent['file'],**stats})
                listening.append({'speaker':speaker,'base_id':'target_02','condition':condition,'file':relative,
                                  'events':truth,'segments':segments,'predictions':[e for e in events if e['accepted']]})
    summary={}
    for condition in sorted({r['condition'] for r in results}):
        subset=[r for r in results if r['condition']==condition]
        summary[condition]={'synthetic_seen_parent_trials':len(subset),
                            'correct_events':sum(r['correct_events'] for r in subset),
                            'false_events':sum(r['false_accepted_events'] for r in subset)}
    report={'independent_human_test_recordings':0,'seen_enrollment_parents':True,
            'training':'two real source families plus three synthetic variants per word','augmentation_policy':policy,
            'warning':'Software robustness diagnostic only. Same source families appear in enrollment and this synthetic test. Never count as independent accuracy.',
            'summary':summary,'rows':results}
    report_path.parent.mkdir(parents=True,exist_ok=True);report_path.write_text(json.dumps(report,indent=2,allow_nan=False))
    preview(output_dir,{'streams':listening,'notice':'SEEN-ENROLLMENT-SOURCE SYNTHETIC DEMO: no independent human test recordings. Do not interpret these results as accuracy on new speech.'})
    print(json.dumps(summary,indent=2));return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,default=Path('data/evaluation/torgo_noisy'))
    parser.add_argument('--output-dir',type=Path,default=Path('data/evaluation/synthetic_keyword_demo'))
    parser.add_argument('--report',type=Path,default=Path('roles/speech/docs/validation/synthetic_keyword_demo.json'))
    parser.add_argument('--augmentation-policy',choices=['mild35','balanced20'],default='mild35')
    args=parser.parse_args();run(args.directory,args.output_dir,args.report,args.augmentation_policy)
