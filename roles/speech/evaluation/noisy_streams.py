"""Download additional TORGO context and assemble annotated noisy speech streams.

Real recorded words + synthetic ambient noise. These are artificial compositions,
not natural sentences or independent new target recordings. No live app access.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
import platform
import re
import shutil
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from sonara.audio.wavio import read_wav, write_wav
from sonara.models.keywords import KeywordSpotter
from roles.speech.evaluation.evaluate_real_corpus import checked_path
from roles.speech.evaluation.evaluate_keyword_streams import event_metrics
from roles.speech.evaluation.torgo import prepare as prepare_sources, take_key, validate, WORDS
from roles.speech.evaluation.memory import peak_process_rss_mib

SEED=20261113
CONDITIONS=('clean','gap_noise','background_20db','background_10db')


def select_additional(rows: list[dict], base: dict, count: int=12) -> dict:
    selection=copy.deepcopy(base)
    excluded={take_key(e) for p in base['profiles'] for e in p['references']+p['queries']}
    forbidden=re.compile(r'\b(?:'+ '|'.join(WORDS)+r')\b',re.I)
    for profile in selection['profiles']:
        # Enrollment-quality failures are retained, with no extra download for failed profiles.
        if profile['speaker'] not in ('F03','M02','M03'):
            continue
        candidates=[r for r in rows if r['speaker']==profile['speaker'] and r['mic']=='headMic'
                    and r['speech_status']=='dysarthria' and .3<=r['duration']<=5
                    and take_key(r) not in excluded and not forbidden.search(r['transcription'])]
        candidates.sort(key=lambda r:hashlib.sha256(('noisy-stream-v1/'+r['file']).encode()).hexdigest())
        if len(candidates)<count:raise ValueError('insufficient independent filler sources')
        profile['queries'].extend({**r,'label':'UNKNOWN','category':'unknown','additional_filler':True}
                                  for r in candidates[:count])
    selection['protocol']='Frozen original enrollment/test takes plus twelve new headMic filler recordings per completed-profile speaker; no score-dependent selection.'
    return selection


def compose(parts: list[tuple[np.ndarray,dict]], seed: int) -> tuple[np.ndarray,list[dict],list[dict],np.ndarray]:
    """Use complete parts; insert 120–350 ms gaps. Keep exact sample-time labels."""
    rng=np.random.default_rng(seed)
    arrays=[];events=[];segments=[];cursor=0
    for i,(audio,meta) in enumerate(parts):
        if i:
            gap=np.zeros(int(rng.uniform(.12,.35)*16000),np.float32)
            arrays.append(gap)
            segments.append({'kind':'gap','start_s':cursor/16000,'end_s':(cursor+len(gap))/16000})
            cursor+=len(gap)
        start=cursor;arrays.append(np.asarray(audio,np.float32));cursor+=len(audio)
        segment={'kind':'speech','source':meta['file'],'text':meta['transcription'],
                 'start_s':start/16000,'end_s':cursor/16000}
        segments.append(segment)
        if meta.get('target'):
            events.append({'intent':meta['label'],'start_s':start/16000,'end_s':cursor/16000,
                           'source':meta['file']})
    # Trailing room-noise interval provides natural streaming look-ahead; no EOF-only flush.
    tail=np.zeros(16000,np.float32);arrays.append(tail)
    segments.append({'kind':'gap','start_s':cursor/16000,'end_s':(cursor+len(tail))/16000})
    audio=np.concatenate(arrays)
    speech_mask=np.zeros(len(audio),bool)
    for s in segments:
        if s['kind']=='speech':speech_mask[round(s['start_s']*16000):round(s['end_s']*16000)]=True
    return audio,events,segments,speech_mask


def add_noise(audio: np.ndarray, speech_mask: np.ndarray, condition: str, seed: int) -> tuple[np.ndarray,dict]:
    if condition not in CONDITIONS:raise ValueError('invalid noise condition')
    rng=np.random.default_rng(seed)
    rms=float(np.sqrt(np.mean(audio[speech_mask].astype(np.float64)**2))) if speech_mask.any() else .03
    t=np.arange(len(audio))/16000
    # Controlled synthetic ambient noise: white hiss, correlated noise and 50 Hz hum.
    white=rng.standard_normal(len(audio))
    correlated=np.convolve(rng.standard_normal(len(audio)),np.ones(17)/17,mode='same')
    noise=.65*white+.25*correlated/.25+.10*np.sin(2*np.pi*50*t)
    noise/=max(float(np.sqrt(np.mean(noise**2))),1e-12)
    if condition=='clean':noise[:]=0
    elif condition=='gap_noise':
        noise*=rms*.5
        noise[speech_mask]=0
    else:
        snr=20 if condition=='background_20db' else 10
        noise*=rms/(10**(snr/20))
        # Extra louder bursts only in gaps, not cuts within the target recording.
        noise[~speech_mask]*=3
    noisy=audio+noise
    gain=min(1.,.95/max(float(np.max(np.abs(noisy),initial=0)),1e-12))
    noisy=(noisy*gain).astype(np.float32)
    noise_rms=float(np.sqrt(np.mean(noise[speech_mask]**2))) if speech_mask.any() else 0.
    measured=20*np.log10(rms/noise_rms) if rms>0 and noise_rms>0 else None
    return noisy,{'condition':condition,'seed':seed,'speech_rms_before_gain':rms,
                  'measured_speech_snr_db':float(measured) if measured is not None else None,
                  'common_gain':gain,'clipped_fraction':float(np.mean(np.abs(noisy)>=.999)),
                  'noise':'synthetic hiss/correlated noise/50 Hz hum; extra gap noise; no disability simulation'}


def preview(directory: Path, manifest: dict) -> None:
    cards=[]
    for stream in manifest['streams']:
        if stream['base_id'] not in ('target_02','repeated','no_target'):
            continue
        text=' / '.join(('['+segment['text']+']' if any(e['source']==segment.get('source')
                        for e in stream['events']) else segment.get('text','[noise gap]'))
                        for segment in stream['segments'])
        title=f"{stream['speaker']} · {stream['base_id']} · {stream['condition']}"
        timing='; '.join(f"{e['intent']}: {e['start_s']:.2f}–{e['end_s']:.2f} s" for e in stream['events']) or 'No target'
        text='Annotated target: '+timing+' | '+text
        cards.append('<article><h2>'+html.escape(title)+'</h2><p>'+html.escape(text)
                     +'</p><audio controls preload="none" src="'+html.escape(stream['file'],quote=True)+'"></audio></article>')
    page='<html><meta charset="utf-8"><title>Sonara composed noisy speech</title>'
    page+='<style>body{font:16px system-ui;max-width:950px;margin:2rem auto;padding:0 1rem}article{border-top:1px solid #ccc;padding:1rem 0}h2{font-size:1rem}audio{width:100%}</style>'
    page+='<h1>Composed TORGO streams</h1><p>Real recorded speech assembled with synthetic ambient noise. Brackets mark the target. These are not natural sentences or WATER/PAIN validation.</p>'
    if manifest.get('notice'):page+='<p><strong>'+html.escape(manifest['notice'])+'</strong></p>'
    page+=''.join(cards)+'</html>'
    (directory/'preview.html').write_text(page,encoding='utf-8')


def prepare(directory: Path, original: Path) -> dict:
    directory.mkdir(parents=True,exist_ok=True)
    base=json.loads((original/'bundle/manifest.json').read_text());validate(base)
    rows=json.loads((original/'rows.json').read_text())
    selection=select_additional(rows,base)
    # Reuse the existing downloaded cache without changing the frozen original manifest.
    for name in ('rows.json','hub.json','revision.json'):
        if (original/name).exists():shutil.copyfile(original/name,directory/name)
    (directory/'bundle').mkdir(exist_ok=True)
    for path in (original/'bundle').iterdir():
        if path.is_file() and path.name!='manifest.json':
            shutil.copyfile(path,directory/'bundle'/path.name)
    manifest=prepare_sources(directory,selection)
    streams=[];failed=[]
    for profile in manifest['profiles']:
        speaker=profile['speaker']
        def load(e):
            a,sr=read_wav(checked_path(directory/'bundle',e))
            if sr!=16000:raise ValueError('16 kHz required')
            return a
        recordings={}
        try:
            for e in profile['references']:
                recordings.setdefault(e['label'],[]).append(KeywordSpotter.audio(load(e)))
            model=KeywordSpotter.enroll(recordings,trim_endpoints=False,allow_few_shot=True,alignment_stride=1,feature_weights=(1.,1.,1.),stride_s=.5,max_candidates=3,refine_boundaries=False)
        except ValueError as exc:
            failed.append({'speaker':speaker,'reason':str(exc)});continue
        model.save(directory/'profiles'/speaker)
        fillers=[e for e in profile['queries'] if e.get('additional_filler')]
        targets=[e for e in profile['queries'] if e['category']=='known']
        plans=[]
        for i,target in enumerate(targets):
            context=[fillers[(i*3+j)%len(fillers)] for j in range(3)]
            position=i%4
            parts=[*context[:position],{**target,'target':True},*context[position:]]
            plans.append((f'target_{i:02d}',parts))
        if targets:
            # Same take repeated is a tracking stress test, not a new independent positive.
            plans.append(('repeated',[fillers[0],{**targets[0],'target':True},fillers[1],{**targets[0],'target':True},fillers[2]]))
        plans.append(('no_target',fillers[6:10]))
        for i,(name,parts) in enumerate(plans):
            clean,events,segments,mask=compose([(load(e),e) for e in parts],SEED+i)
            for condition in CONDITIONS:
                noisy,noise=add_noise(clean,mask,condition,SEED+1000+i)
                relative=f'streams/{speaker}/{name}_{condition}.wav'
                write_wav(directory/relative,noisy,16000)
                streams.append({'speaker':speaker,'base_id':name,'condition':condition,'file':relative,
                                'duration_s':len(noisy)/16000,'events':events,'segments':segments,'noise':noise,
                                'wav_sha256':hashlib.sha256((directory/relative).read_bytes()).hexdigest()})
        # Noise-only negative has no speech sources or target events.
        clean=np.zeros(8*16000,np.float32);mask=np.zeros(len(clean),bool)
        noisy,noise=add_noise(clean,mask,'gap_noise',SEED)
        relative=f'streams/{speaker}/noise_only.wav';write_wav(directory/relative,noisy,16000)
        streams.append({'speaker':speaker,'base_id':'noise_only','condition':'noise_only','file':relative,
                        'duration_s':8.,'events':[],'segments':[],'noise':noise,
                        'wav_sha256':hashlib.sha256((directory/relative).read_bytes()).hexdigest()})
    result={'version':1,'source_repository':manifest['repository'],'source_revision':manifest['revision'],
            'seed':SEED,'streams':streams,'failed_profiles':failed,
            'new_filler_source_count':sum(e.get('additional_filler',False) for p in manifest['profiles'] for e in p['queries']),
            'independent_positive_source_count':len({e['source'] for s in streams for e in s['events']}),
            'artificially_composed':True,'noise_is_synthetic':True,'natural_sentence_accuracy':False,
            'target_sources_reused_from_prior_evaluation':True,'variants_are_independent_recordings':False}
    (directory/'streams.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    preview(directory,result)
    print(f'Built {len(streams)} annotated streams in {directory}',flush=True)
    return result


def evaluate(directory: Path, output: Path) -> dict:
    manifest=json.loads((directory/'streams.json').read_text())
    profiles={};rows=[]
    for stream in manifest['streams']:
        speaker=stream['speaker']
        if speaker not in profiles:profiles[speaker]=KeywordSpotter.load(directory/'profiles'/speaker)
        model=profiles[speaker];model.reset()
        path=checked_path(directory,stream)
        audio,sr=read_wav(path,max_seconds=60)
        if sr!=16000:raise ValueError('16 kHz required')
        events=[];started=time.perf_counter()
        for i in range(0,len(audio),800):events.extend(e.to_dict() for e in model.feed(audio[i:i+800]))
        elapsed=time.perf_counter()-started
        stats=event_metrics(stream['events'],events,len(audio)/16000)
        # Diagnostic only: nearest label with overlapping location, even if rejected.
        nearest=sum(any(e['best']==t['intent'] and max(0,min(e['end_s'],t['end_s'])-max(e['start_s'],t['start_s']))
                        /(max(e['end_s'],t['end_s'])-min(e['start_s'],t['start_s']))>=.3 for e in events)
                    for t in stream['events'])
        rows.append({'speaker':speaker,'base_id':stream['base_id'],'condition':stream['condition'],
                     'file':stream['file'],'wav_sha256':stream['wav_sha256'],'truth':stream['events'],
                     'noise':stream['noise'],
                     'duration_s':len(audio)/sr,'processing_s':elapsed,'nearest_localized_before_rejection':nearest,
                     **stats})
        print(f'{speaker}/{stream["base_id"]}/{stream["condition"]}: '
              f'{stats["correct_events"]}/{stats["truth_events"]} accepted; {stats["false_accepted_events"]} false',flush=True)
    summary={}
    for condition in sorted({r['condition'] for r in rows}):
        subset=[r for r in rows if r['condition']==condition]
        total=sum(r['truth_events'] for r in subset);duration=sum(r['duration_s'] for r in subset)
        correct=sum(r['correct_events'] for r in subset);false=sum(r['false_accepted_events'] for r in subset)
        summary[condition]={'streams':len(subset),'target_occurrences':total,'correct_events':correct,
                            'event_recall':correct/total if total else None,'false_accepted_events':false,
                            'false_accepted_events_per_hour':false*3600/duration,
                            'nearest_localized_before_rejection':sum(r['nearest_localized_before_rejection'] for r in subset),
                            'audio_duration_s':duration,'real_time_factor':sum(r['processing_s'] for r in subset)/duration}
    report={k:v for k,v in manifest.items() if k!='streams'}
    report.update({'summary':summary,'rows':rows,'peak_process_rss_mib':peak_process_rss_mib(),
                   'platform':platform.platform(),'machine':platform.machine(),
                   'python':platform.python_version(),'numpy':np.__version__,
                   'warning':'Repeated/noisy variants are not independent positives. Artificial sentence assembly; no threshold tuning; not clinical or WATER/PAIN validation.'})
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps(summary,indent=2));return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['prepare','evaluate'])
    parser.add_argument('--directory',type=Path,default=Path('data/evaluation/torgo_noisy'))
    parser.add_argument('--original',type=Path,default=Path('data/evaluation/torgo'))
    parser.add_argument('--output',type=Path,default=Path('roles/speech/docs/validation/noisy_streams_laptop.json'))
    args=parser.parse_args()
    prepare(args.directory,args.original) if args.command=='prepare' else evaluate(args.directory,args.output)
