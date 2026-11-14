"""Build a separate feature-only candidate or score a WAV; never activates Sonara."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from sonara.audio.wavio import read_wav
from sonara.models.personal import PersonalWordCandidate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--sessions',type=Path,nargs='+')
    parser.add_argument('--wav',type=Path)
    parser.add_argument('--context',choices=['requests','confirmation'],default='requests')
    args = parser.parse_args()
    if bool(args.sessions) == bool(args.wav):
        parser.error('Choose --sessions to build OR --wav to score')
    if args.sessions:
        model = PersonalWordCandidate(); seen = set()
        for session in args.sessions:
            for path in sorted((session/'recordings/enrollment').glob('*/*.wav')):
                audio,sr = read_wav(path)
                if sr != 16000: raise ValueError('16 kHz required')
                family = hashlib.sha256(audio.tobytes()).hexdigest()
                if family in seen: raise ValueError('Duplicate enrollment source')
                seen.add(family)
                model.add(path.parent.name,family,audio)
                # Augment only enrollment sources; speed changes pitch and length together.
                centered = audio-audio.mean()
                from sonara.audio.vad import trim_silence
                centered = trim_silence(centered,16000,pad_ms=80)
                for rate,gain in ((.94,.85),(1.06,1.15)):
                    variant = np.interp(np.arange(0,len(centered)-1,rate),np.arange(len(centered)),centered)*gain
                    # Match the study: trim once before augmentation, not again afterward.
                    weights = np.repeat([1.,.5,.25],13)
                    from sonara.models.features import mfcc,FeatureConfig
                    seq = (mfcc(variant.astype(np.float32),config=FeatureConfig())*weights).astype(np.float32)[::2]
                    model.sequences.append(seq); model.labels.append(path.parent.name); model.families.append(family)
        if not seen or len(model.sequences)>400: raise ValueError('Need 1–133 independent sources')
        model.save(args.candidate)
        print(f'Saved {len(seen)} real sources / {len(model.sequences)} references to {args.candidate}')
    else:
        audio,sr = read_wav(args.wav)
        if sr != 16000: raise ValueError('16 kHz required')
        result = PersonalWordCandidate.load(args.candidate).predict(audio,args.context)
        print(json.dumps(result.to_dict(),indent=2))

if __name__ == '__main__': main()
