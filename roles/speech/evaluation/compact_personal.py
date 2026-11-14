"""Select balanced real-source medoids for a compact, single-pass request profile."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from sonara.models.personal import PersonalWordCandidate,CONTEXTS
from sonara.models.dtw import dtw_distances


def compact(source: PersonalWordCandidate, per_intent: int=3) -> PersonalWordCandidate:
    if not 2<=per_intent<=10:raise ValueError('Choose 2–10 references per request')
    result=PersonalWordCandidate()
    result.speech_gate=True
    result.intent_margins={'FOOD':.025}
    for label in CONTEXTS['requests']:
        # First sequence of each family is real; synthetic siblings never become medoids.
        indices=[i for i,l in enumerate(source.labels) if l==label and source.families.index(source.families[i])==i]
        if len(indices)<per_intent:raise ValueError(f'{label}: insufficient independent references')
        matrix=np.array([dtw_distances(source.sequences[i],[source.sequences[j] for j in indices]) for i in indices])
        nearest=np.full(len(indices),np.inf);chosen=[]
        for _ in range(per_intent):
            costs=np.minimum(nearest[:,None],matrix).sum(axis=0)
            costs[chosen]=np.inf
            j=int(np.argmin(costs));chosen.append(j);nearest=np.minimum(nearest,matrix[:,j])
        for j in chosen:
            i=indices[j]
            result.sequences.append(source.sequences[i].copy())
            result.labels.append(label);result.families.append(source.families[i])
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--per-intent',type=int,default=3)
    args=parser.parse_args()
    model=compact(PersonalWordCandidate.load(args.source),args.per_intent)
    model.save(args.output)
    print(f'Saved {len(model.sequences)} independent request templates; speech gate enabled; FOOD margin 0.025')

if __name__=='__main__':main()
