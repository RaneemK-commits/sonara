"""Session-held-out development comparison. Similar-word negatives are evaluated without threshold tuning."""
import json
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from sonara.audio.wavio import read_wav
from sonara.audio.vad import trim_silence
from sonara.models.features import FeatureConfig, mfcc
from sonara.models.dtw import dtw_distances


def run():
    root = Path('data/profiles')
    records = []
    seen = set()
    import hashlib
    for session in ('02', '03', '04'):
        for path in sorted((root / f'laptop_session_{session}/recordings/enrollment').glob('*/*.wav')):
            audio, sr = read_wav(path)
            if sr != 16000: raise ValueError('16 kHz required')
            digest = hashlib.sha256(audio.tobytes()).hexdigest()
            if digest in seen: raise ValueError('Duplicate recording across enrollment sources')
            seen.add(digest)
            records.append((session, path.parent.name, audio))
    report = {'sources': len(records), 'warning': 'Development session cross-validation; Known final test recordings untouched; similar-word negatives evaluated without tuning. Fixed threshold 0.8 and margin 0.12. Speed variants change pitch and duration together.', 'variants': {}}
    for variant in ('baseline', 'trimmed', 'trimmed_weighted', 'trimmed_weighted_augmented'):
        features = []
        augmented = []
        weights = np.repeat([1., .5, .25], 13) if 'weighted' in variant else np.ones(39)
        for session, label, audio in records:
            audio = audio - audio.mean()
            if variant != 'baseline': audio = trim_silence(audio, 16000, pad_ms=80)
            if len(audio) < 2400: raise ValueError('Too little speech')
            features.append((mfcc(audio, config=FeatureConfig()) * weights).astype(np.float32)[::2])
            variants = []
            if 'augmented' in variant:
                for rate, gain in ((.94, .85), (1.06, 1.15)):
                    changed = np.interp(np.arange(0,len(audio)-1,rate),np.arange(len(audio)),audio)*gain
                    variants.append((mfcc(changed.astype(np.float32), config=FeatureConfig())*weights).astype(np.float32)[::2])
            augmented.append(variants)
        rows = []
        for held in ('02','03','04'):
            for context, labels in [('requests', {'WATER','HELP','FOOD','PAIN','BATHROOM'}), ('confirmation', {'YES','NO'})]:
                training = [i for i,r in enumerate(records) if r[0] != held and r[1] in labels]
                refs = []; families = []
                for i in training:
                    for seq in [features[i]] + augmented[i]:
                        refs.append(seq); families.append(i)
                for index, (session, expected, _) in enumerate(records):
                    if session != held or expected not in labels: continue
                    distances = np.concatenate([dtw_distances(features[index],refs[start:start+16],band=.2) for start in range(0,len(refs),16)])
                    family_scores = {}
                    for i,d in zip(families,distances): family_scores[i] = min(family_scores.get(i,float('inf')),float(d))
                    scores = {label: float(np.mean(sorted(d for i,d in family_scores.items() if records[i][1]==label)[:2])) for label in labels}
                    ranking = sorted(scores,key=scores.get)
                    best = ranking[0]; distance = scores[best]; gap = scores[ranking[1]]-distance
                    rows.append({'session':held,'context':context,'expected':expected,'best':best,'distance':distance,'margin':gap,'accepted':distance<=.8 and gap>=.12})
        negative_rows = []
        for manifest in sorted(root.glob('laptop_session_*/recording_sessions/*/manifest.json')):
            for entry in json.loads(manifest.read_text()):
                if entry.get('expected') != 'UNKNOWN': continue
                source = (manifest.parent / entry['file']).resolve()
                if not source.is_relative_to(manifest.parent.resolve()):
                    raise ValueError('Invalid manifest audio path')
                audio, sr = read_wav(source)
                if sr != 16000: raise ValueError('16 kHz required')
                if hashlib.sha256(audio.tobytes()).hexdigest() in seen:
                    raise ValueError('Negative recording duplicates enrollment')
                audio = audio - audio.mean()
                if variant != 'baseline': audio = trim_silence(audio,16000,pad_ms=80)
                if len(audio)<2400: raise ValueError('Negative recording has too little speech')
                query = (mfcc(audio,config=FeatureConfig())*weights).astype(np.float32)[::2]
                for context, labels in [('requests', {'WATER','HELP','FOOD','PAIN','BATHROOM'}), ('confirmation', {'YES','NO'})]:
                    refs, families = [], []
                    for i, record in enumerate(records):
                        if record[1] not in labels: continue
                        for seq in [features[i]]+augmented[i]:
                            refs.append(seq); families.append(i)
                    distances = np.concatenate([dtw_distances(query,refs[start:start+16],band=.2) for start in range(0,len(refs),16)])
                    family_scores = {}
                    for i,d in zip(families,distances): family_scores[i] = min(family_scores.get(i,float('inf')),float(d))
                    scores = {label:float(np.mean(sorted(d for i,d in family_scores.items() if records[i][1]==label)[:2])) for label in labels}
                    ranking = sorted(scores,key=scores.get)
                    distance = scores[ranking[0]]; gap = scores[ranking[1]]-distance
                    negative_rows.append({'prompt':entry['prompt'],'context':context,'best':ranking[0],
                                          'distance':distance,'margin':gap,'accepted':distance<=.8 and gap>=.12})
        negative_summary = {context:{'trials':sum(r['context']==context for r in negative_rows),
                                    'false_accepts':sum(r['context']==context and r['accepted'] for r in negative_rows)}
                            for context in ('requests','confirmation')}
        summary = {}
        for context in ('requests','confirmation'):
            selected = [r for r in rows if r['context']==context]
            summary[context] = {'trials':len(selected),'nearest_correct':sum(r['best']==r['expected'] for r in selected),'accepted_correct':sum(r['accepted'] and r['best']==r['expected'] for r in selected),'accepted_wrong':sum(r['accepted'] and r['best']!=r['expected'] for r in selected)}
        report['variants'][variant] = {'summary':summary,'rows':rows,'negative_summary':negative_summary,'negative_rows':negative_rows}
        destination = root / 'personal_session_development.json'
        destination.write_text(json.dumps(report,indent=2))
        print(variant,summary,negative_summary,flush=True)

if __name__ == '__main__': run()
