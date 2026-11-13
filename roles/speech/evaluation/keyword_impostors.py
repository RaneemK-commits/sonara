"""Same-word, different-speaker negative tests; not biometric validation."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from sonara.audio.wavio import read_wav
from sonara.models.keywords import KeywordSpotter
from roles.speech.evaluation.keyword_ablation import VARIANTS,recordings
from roles.speech.evaluation.evaluate_real_corpus import checked_path


def run(directory: Path,output: Path) -> dict:
    manifest=json.loads((directory/'bundle/manifest.json').read_text());report={'variants':{}}
    for name in ('refined_30ms','refined_augmented_40ms'):
        rows=[]
        for profile in manifest['profiles']:
            if profile['speaker'] not in ('F03','M02','M03'):continue
            model=KeywordSpotter.enroll(recordings(directory,profile['speaker']),trim_endpoints=False,
                                         allow_few_shot=True,seed=412,**VARIANTS[name])
            for entry in profile['queries']:
                if entry['category']!='impostor':continue
                audio,sr=read_wav(checked_path(directory/'bundle',entry))
                if sr!=16000:raise ValueError('16 kHz required')
                # Look-ahead is explicit and identical for all negatives.
                audio=np.r_[audio,np.zeros(16000,np.float32)].astype(np.float32)
                model.reset();events=[]
                for i in range(0,len(audio),800):events.extend(e.to_dict() for e in model.feed(audio[i:i+800]))
                accepted=[e for e in events if e['accepted']]
                rows.append({'profile':profile['speaker'],'source':entry['file'],
                             'spoken_word':entry['transcription'],'truth':'UNKNOWN','accepted_events':accepted})
        report['variants'][name]={'trials':len(rows),'trials_with_false_accepts':sum(bool(r['accepted_events']) for r in rows),
                                 'false_accepted_events':sum(len(r['accepted_events']) for r in rows),'rows':rows}
    report['warning']='Speaker-dependent matching is not speaker authentication. Few-shot corpus profiles and reused development data; no threshold tuning on these queries.'
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps({k:{x:y for x,y in v.items() if x!='rows'} for k,v in report['variants'].items()},indent=2))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,default=Path('data/evaluation/torgo_noisy'))
    parser.add_argument('--output',type=Path,default=Path('roles/speech/docs/validation/keyword_impostors_laptop.json'))
    args=parser.parse_args();run(args.directory,args.output)
