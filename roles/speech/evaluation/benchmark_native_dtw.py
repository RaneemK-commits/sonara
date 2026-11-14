"""Paired exact NumPy/native candidate benchmark on the same consented WAV."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import platform
import sys
import time
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from sonara.models.personal import PersonalWordCandidate
from sonara.models.native_dtw import NativeDTW
from sonara.audio.wavio import read_wav


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--library',type=Path,required=True)
    parser.add_argument('--wav',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--repetitions',type=int,default=3)
    args=parser.parse_args()
    if not 1<=args.repetitions<=10:parser.error('repetitions must be 1–10')
    audio,sr=read_wav(args.wav)
    if sr!=16000:parser.error('16 kHz required')
    report={'machine':platform.machine(),'audio_seconds':len(audio)/sr,'engines':{}}
    for name in ('numpy','native'):
        model=PersonalWordCandidate.load(args.candidate)
        model._native=NativeDTW(str(args.library.resolve())) if name=='native' else None
        trials=[]
        for _ in range(args.repetitions):
            start=time.perf_counter();result=model.predict(audio,threshold=.75,required_margin=0)
            trials.append({'wall_ms':(time.perf_counter()-start)*1000,**result.to_dict()})
        report['engines'][name]=trials
    reference=report['engines']['numpy'][0]
    for trial in report['engines']['native']:
        if trial['best']!=reference['best'] or trial['accepted']!=reference['accepted']:
            raise ValueError('Native decision differs from NumPy')
        for label,value in reference['scores'].items():
            if not np.isclose(value,trial['scores'][label],atol=1e-9,rtol=0):
                raise ValueError('Native score differs from NumPy')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2))
    print(json.dumps({name:float(np.median([r['wall_ms'] for r in rows]))
                      for name,rows in report['engines'].items()},indent=2))

if __name__=='__main__':main()
