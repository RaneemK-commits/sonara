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


def focused_word(audio: np.ndarray) -> np.ndarray:
    """Candidate-only retry: ignore isolated energy spikes; retain internal pauses."""
    audio = np.asarray(audio,dtype=np.float32)
    audio = audio-audio.mean()
    frame=320
    n=len(audio)//frame
    if n<3:
        return audio
    energy=np.sqrt(np.mean(audio[:n*frame].reshape(n,frame).astype(float)**2,axis=1))
    peak=float(energy.max()); floor=float(np.percentile(energy,10))
    threshold=max(1e-5,min(max(floor*3,peak*.1),peak*.3))
    active=energy>threshold
    retained=np.zeros(n,bool)
    start=0
    while start<n:
        if not active[start]:
            start+=1
            continue
        end=start+1
        while end<n and active[end]:
            end+=1
        if end-start>=3:
            retained[start:end]=True
        start=end
    indices=np.flatnonzero(retained)
    if not len(indices):
        return audio[:0]
    return audio[max(0,indices[0]-4)*frame:min(len(audio),(indices[-1]+5)*frame)]


def has_speech_activity(audio: np.ndarray, min_rms: float=0.) -> bool:
    """Reject steady room noise/clicks before DTW; intended for padded Talk clips."""
    audio=np.asarray(audio,dtype=np.float32)
    if audio.ndim!=1 or not 4800<=len(audio)<=80000 or not np.isfinite(audio).all():
        return False
    audio=audio-audio.mean()
    if np.sqrt(np.mean(audio.astype(float)**2))<min_rms:
        return False
    frame=320
    energy=np.sqrt(np.mean(audio[:len(audio)//frame*frame].reshape(-1,frame).astype(float)**2,axis=1))
    floor=max(float(np.percentile(energy,20)),1e-6)
    if float(np.percentile(energy,95))/floor<2.5:
        return False
    voiced=energy>max(2*floor,2*min_rms)
    return bool(np.any(np.convolve(voiced.astype(int),np.ones(3,dtype=int),'valid')>=3))


class PersonalWordCandidate:
    def __init__(self):
        from .native_dtw import engine_from_env
        self._native = engine_from_env()
        self.min_rms = 0.
        self.speech_gate = False
        self.intent_margins: dict[str,float] = {}
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
            if self.speech_gate and not has_speech_activity(audio,self.min_rms):
                return Prediction(None,None,float('inf'),0.,threshold,{},
                                  (time.perf_counter()-started)*1000,'no clear speech activity')
            query = self.features(audio)
        except (ValueError, TypeError) as exc:
            return Prediction(None,None,float('inf'),0.,threshold,{},reason=str(exc))
        result = self._match(query,context,threshold,required_margin)
        if not result.accepted and context=='requests' and required_margin>0:
            cropped=focused_word(audio)
            # Retry only a substantial endpoint reduction, preserving a meaningful word span.
            if 2400<=len(cropped)<=.75*len(audio):
                weights=np.repeat([1.,.5,.25],13)
                retry_query=(mfcc(cropped,config=FeatureConfig())*weights).astype(np.float32)[::2]
                retry=self._match(retry_query,context,threshold,required_margin)
                if retry.accepted and retry.best==result.best:
                    result=retry
                    result.reason='accepted after word-boundary retry'
        result.latency_ms=(time.perf_counter()-started)*1000
        return result

    def _match(self, query: np.ndarray, context: str, threshold: float,
               required_margin: float) -> Prediction:
        indices = [i for i,label in enumerate(self.labels) if label in CONTEXTS[context]]
        if len({self.labels[i] for i in indices}) != len(CONTEXTS[context]):
            return Prediction(None,None,float('inf'),0.,threshold,{},reason='Incomplete context')
        groups: dict[str,dict[str,float]] = {}
        for start in range(0,len(indices),16):
            selected = indices[start:start+16]
            matcher=self._native.distances if self._native is not None else dtw_distances
            distances = matcher(query,[self.sequences[i] for i in selected],band=.2)
            for i,distance in zip(selected,distances):
                family = groups.setdefault(self.labels[i],{})
                family[self.families[i]] = min(family.get(self.families[i],float('inf')),float(distance))
        if any(len(families)<2 for families in groups.values()):
            return Prediction(None,None,float('inf'),0.,threshold,{},reason='Need two independent sources per label')
        scores = {label:float(np.mean(sorted(families.values())[:2])) for label,families in groups.items()}
        ranked = sorted(scores,key=scores.get)
        best = ranked[0]; distance = scores[best]; margin = scores[ranked[1]]-distance
        intent_margin=max(required_margin,self.intent_margins.get(best,0.))
        accepted = distance <= threshold and margin >= intent_margin
        return Prediction(best if accepted else None,best,distance,margin,threshold,scores,
                          0.,
                          ('closest-label demo; confirmation required' if intent_margin==0 else '')
                          if accepted else 'distant or ambiguous')

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True,exist_ok=False)
        archive = directory/'references.npz'
        np.savez_compressed(archive,**{f's{i}':seq for i,seq in enumerate(self.sequences)})
        metadata = {'version':2,'labels':self.labels,'families':self.families,
                    'speech_gate':self.speech_gate,'intent_margins':self.intent_margins,'min_rms':self.min_rms,
                    'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
                    'threshold':.8,'margin':.12,'feature_weights':[1.,.5,.25],
                    'trim_pad_ms':80,'alignment_stride':2,
                    'warning':'Experimental. Rejection unresolved; confirmation confuses snow with NO. Not an active production profile.'}
        (directory/'candidate.json').write_text(json.dumps(metadata,indent=2))

    @classmethod
    def load(cls, directory: Path) -> PersonalWordCandidate:
        metadata = json.loads((directory/'candidate.json').read_text())
        archive = directory/'references.npz'
        if metadata.get('version') not in (1,2) or hashlib.sha256(archive.read_bytes()).hexdigest() != metadata['sha256']:
            raise ValueError('Invalid candidate version or checksum')
        model = cls()
        model.min_rms=metadata.get('min_rms',0.)
        if not isinstance(model.min_rms,(int,float)) or not np.isfinite(model.min_rms) or not 0<=model.min_rms<=.05:
            raise ValueError('Invalid speech level floor')
        model.speech_gate=metadata.get('speech_gate',False)
        model.intent_margins=metadata.get('intent_margins',{})
        if not isinstance(model.speech_gate,bool) or not isinstance(model.intent_margins,dict):
            raise ValueError('Invalid candidate policy')
        if any(label not in sum(CONTEXTS.values(),()) or not isinstance(value,(int,float)) or
               not np.isfinite(value) or value<0 for label,value in model.intent_margins.items()):
            raise ValueError('Invalid intent margins')
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
