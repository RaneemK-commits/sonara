"""Evaluate fresh annotated WAV streams against an experimental keyword profile.

Manifest: {"streams":[{"file":"heldout.wav","events":[{"intent":"WATER",
"start_s":1.2,"end_s":1.8}]}]}. Empty events means an UNKNOWN stream.
WAVs: mono PCM16, 16 kHz, <=10 minutes each; audio is read in 50 ms chunks.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from sonara.models.keywords import KeywordSpotter
from roles.speech.evaluation.compare_keywords import overlap
from roles.speech.evaluation.memory import peak_process_rss_mib


def event_metrics(truth: list[dict], detections: list[dict], duration_s: float) -> dict:
    matched=set();false=duplicates=0;delays=[]
    for event in sorted((e for e in detections if e['accepted']),key=lambda e:e['observed_until_s']):
        candidates=[(i,overlap((event['start_s'],event['end_s']),(t['start_s'],t['end_s'])))
                    for i,t in enumerate(truth) if event['intent']==t['intent']]
        candidates=[(i,v) for i,v in candidates if v>=.3]
        if not candidates:
            false+=1
            continue
        available=[pair for pair in candidates if pair[0] not in matched]
        i,_=max(available or candidates,key=lambda pair:pair[1])
        if not available:
            duplicates+=1
            false+=1
            continue
        matched.add(i)
        delays.append(event['observed_until_s']-truth[i]['end_s'])
    accepted=sum(e['accepted'] for e in detections)
    return {'truth_events':len(truth),'correct_events':len(matched),'missed_events':len(truth)-len(matched),
            'event_recall':len(matched)/len(truth) if truth else None,
            'precision':len(matched)/accepted if accepted else None,
            'false_accepted_events':false,'duplicate_accepted_events':duplicates,
            'false_accepted_events_per_hour':false*3600/duration_s if duration_s else None,
            'audio_duration_s':duration_s,'detection_delay_s':delays}


def run(profile: Path, manifest_path: Path, output: Path) -> dict:
    model=KeywordSpotter.load(profile)
    manifest=json.loads(manifest_path.read_text())
    if not 1<=len(manifest['streams'])<=100:
        raise ValueError('expected 1–100 held-out WAV streams')
    reports=[]
    seen=set()
    for entry in manifest['streams']:
        path=(manifest_path.parent/entry['file']).resolve()
        digest=hashlib.sha256()
        with path.open('rb') as source:
            for block in iter(lambda:source.read(1024*1024),b''):digest.update(block)
        fingerprint=digest.hexdigest()
        if fingerprint in seen:raise ValueError('duplicate evaluation WAV')
        seen.add(fingerprint)
        model.reset();events=[]
        with wave.open(str(path),'rb') as wav:
            duration=wav.getnframes()/16000
            if (wav.getframerate()!=16000 or wav.getnchannels()!=1 or wav.getsampwidth()!=2
                    or wav.getcomptype()!='NONE' or not .3<=duration<=600):
                raise ValueError('streams must be mono PCM16 / 16 kHz, 0.3–600 s')
            truth=entry['events']
            for event in truth:
                if (event['intent'] not in model.references.classes
                        or not 0<=event['start_s']<event['end_s']<=duration):
                    raise ValueError('invalid intent or annotated time interval')
            started=time.perf_counter();decoded_samples=0
            while data:=wav.readframes(800):
                chunk=np.frombuffer(data,dtype='<i2').astype(np.float32)/32768.
                decoded_samples+=len(chunk)
                events.extend(e.to_dict() for e in model.feed(chunk))
            if decoded_samples!=wav.getnframes():
                raise ValueError('truncated WAV stream')
            elapsed=time.perf_counter()-started
        reports.append({'file':entry['file'],'wav_sha256':fingerprint,'processing_s':elapsed,
                        'real_time_factor':elapsed/duration,**event_metrics(truth,events,duration),
                        'truth':truth,'detections':events})
    duration=sum(r['audio_duration_s'] for r in reports)
    correct=sum(r['correct_events'] for r in reports);count=sum(r['truth_events'] for r in reports)
    false=sum(r['false_accepted_events'] for r in reports)
    report={'kind':'experimental_keyword_stream_evaluation','streams':reports,
            'summary':{'audio_duration_s':duration,'truth_events':count,'correct_events':correct,
                       'event_recall':correct/count if count else None,'false_accepted_events':false,
                       'false_accepted_events_per_hour':false*3600/duration,
                       'real_time_factor':sum(r['processing_s'] for r in reports)/duration},
            'peak_process_rss_mib':peak_process_rss_mib(),
            'warning':'Use independent held-out streams. Enrollment-source independence cannot be verified from feature-only profiles. No test threshold tuning; no clinical or speaker-identity claim.'}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps(report['summary'],indent=2))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',type=Path,required=True)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=Path('results/keyword_streams.json'))
    args=parser.parse_args()
    run(args.profile,args.manifest,args.output)
