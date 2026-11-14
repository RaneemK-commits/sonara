"""Keep every reference, adding idle-speech and FOOD ambiguity checks."""
import argparse
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from sonara.models.personal import PersonalWordCandidate,CONTEXTS


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--food-margin',type=float,default=.025)
    parser.add_argument('--min-rms',type=float,default=.003)
    parser.add_argument('--margin',type=float,default=.01)
    args=parser.parse_args()
    if not np.isfinite(args.min_rms) or not 0<=args.min_rms<=.05:
        parser.error('Speech level floor must be finite and between 0 and 0.05')
    if not np.isfinite(args.margin) or not 0<=args.margin<=.2:
        parser.error('Margin must be finite and between 0 and 0.2')
    if not np.isfinite(args.food_margin) or not 0<=args.food_margin<=.2:
        parser.error('FOOD margin must be finite and between 0 and 0.2')
    model=PersonalWordCandidate.load(args.source)
    model.speech_gate=True
    model.min_rms=args.min_rms
    model.intent_margins={label:args.margin for label in CONTEXTS['requests']}
    model.intent_margins['FOOD']=max(args.food_margin,args.margin)
    model.save(args.output)
    print(f'Saved {len(model.sequences)} unchanged references with speech/FOOD guards')

if __name__=='__main__':main()
