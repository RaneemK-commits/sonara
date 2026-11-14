"""Separate experimental personal-word candidate; never selects an active profile.

Fixed rejection limits reproduce the session study. This is not the production
profile format: weighted features and source families must survive reload.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time

import numpy as np

from sonara.audio.vad import trim_silence
from .classifier import Prediction
from .dtw import dtw_distances
from .features import FeatureConfig, mfcc

CONTEXTS = {'requests': ('WATER', 'HELP', 'FOOD', 'PAIN', 'BATHROOM'),
            'confirmation': ('YES', 'NO')}


class PersonalWordCandidate:
    def __init__(self):
        self.sequences: list[np.ndarray] = []
        self.labels: list[str] = []
        self.families: list[str] = []

    @staticmethod
    def features(audio: np.ndarray) -> np.ndarray:
        audio = np.asarray(audio, dtype=np.float32)
        if (audio.ndim != 1 or not 4800 <= audio.size <= 80000 or
                not np.isfinite(audio).all() or np.max(np.abs(audio)) > 1.001):
            raise ValueError('Expected 0.3–5 seconds of finite 16 kHz mono audio')
        if np.mean(np.abs(audio) >= .999) > .05:
            raise ValueError('Clipped recording')
        audio = audio - audio.mean()
        if np.sqrt(np.mean(audio.astype(np.float64)**2)) < .00003:
            raise ValueError('Silent recording')
        audio = trim_silence(audio, 16000, pad_ms=80)
        if len(audio) < 2400:
            raise ValueError('Too little speech')
        weights = np.repeat([1., .5, .25], 13)
        return (mfcc(audio, config=FeatureConfig()) * weights).astype(np.float32)[::2]

    def add(self, label: str, family: str, audio: np.ndarray) -> None:
        if label not in sum(CONTEXTS.values(), ()):
            raise ValueError('Unknown label')
        if len(self.sequences) >= 400:
            raise ValueError('Candidate reference limit exceeded')
        if family in self.families and any(l != label for l,f in zip(self.labels,self.families) if f == family):
            raise ValueError('Source family has conflicting labels')
        self.sequences.append(self.features(audio))
        self.labels.append(label)
        self.families.append(family)

    def predict(self, audio: np.ndarray, context: str = 'requests', *,
                threshold: float = .8, required_margin: float = .12) -> Prediction:
        if context not in CONTEXTS:
            raise ValueError('Context must be requests or confirmation')
        if not np.isfinite(threshold) or threshold <= 0 or not np.isfinite(required_margin) or required_margin < 0:
            raise ValueError('Invalid rejection limits')
        started = time.perf_counter()
        try:
            query = self.features(audio)
        except (ValueError, TypeError) as exc:
            return Prediction(None,None,float('inf'),0.,threshold,{},reason=str(exc))
        indices = [i for i,label in enumerate(self.labels) if label in CONTEXTS[context]]
        if len({self.labels[i] for i in indices}) != len(CONTEXTS[context]):
            return Prediction(None,None,float('inf'),0.,threshold,{},reason='Incomplete context')
        groups: dict[str,dict[str,float]] = {}
        for start in range(0,len(indices),16):
            selected = indices[start:start+16]
            distances = dtw_distances(query,[self.sequences[i] for i in selected],band=.2)
            for i,distance in zip(selected,distances):
                family = groups.setdefault(self.labels[i],{})
                family[self.families[i]] = min(family.get(self.families[i],float('inf')),float(distance))
        if any(len(families)<2 for families in groups.values()):
            return Prediction(None,None,float('inf'),0.,threshold,{},reason='Need two independent sources per label')
        scores = {label:float(np.mean(sorted(families.values())[:2])) for label,families in groups.items()}
        ranked = sorted(scores,key=scores.get)
        best = ranked[0]; distance = scores[best]; margin = scores[ranked[1]]-distance
        accepted = distance <= threshold and margin >= required_margin
        return Prediction(best if accepted else None,best,distance,margin,threshold,scores,
                          (time.perf_counter()-started)*1000,
                          '' if accepted else 'distant or ambiguous')

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True,exist_ok=False)
        archive = directory/'references.npz'
        np.savez_compressed(archive,**{f's{i}':seq for i,seq in enumerate(self.sequences)})
        metadata = {'version':1,'labels':self.labels,'families':self.families,
                    'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
                    'threshold':.8,'margin':.12,'feature_weights':[1.,.5,.25],
                    'trim_pad_ms':80,'alignment_stride':2,
                    'warning':'Experimental. Rejection unresolved; confirmation confuses snow with NO. Not an active production profile.'}
        (directory/'candidate.json').write_text(json.dumps(metadata,indent=2))

    @classmethod
    def load(cls, directory: Path) -> PersonalWordCandidate:
        metadata = json.loads((directory/'candidate.json').read_text())
        archive = directory/'references.npz'
        if metadata.get('version') != 1 or hashlib.sha256(archive.read_bytes()).hexdigest() != metadata['sha256']:
            raise ValueError('Invalid candidate version or checksum')
        model = cls()
        model.labels,model.families = metadata['labels'],metadata['families']
        if not 1 <= len(model.labels) <= 400 or len(model.labels) != len(model.families):
            raise ValueError('Invalid reference counts')
        with np.load(archive,allow_pickle=False) as data:
            for i,label in enumerate(model.labels):
                seq = data[f's{i}']
                if (label not in sum(CONTEXTS.values(),()) or seq.ndim != 2 or
                        seq.shape[1] != 39 or not 1 <= len(seq) <= 300 or not np.isfinite(seq).all()):
                    raise ValueError('Invalid candidate sequence')
                model.sequences.append(seq.astype(np.float32))
        return model
