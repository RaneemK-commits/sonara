"""Experimental personalized keywords inside phrases, without a controller side effect.

Uses enrollment-fitted shared MFCC scaling, free-endpoint DTW proposals and
whole-span all-intent rescoring. Existing utterance-CMVN profiles cannot be reused.
A separate keyword profile and continuous-speech negative validation are required.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, replace
from collections import OrderedDict
from pathlib import Path

import numpy as np

from ..audio.vad import trim_silence
from .classifier import Prediction, PrototypeClassifier
from .features import FeatureConfig, mfcc
from .subsequence import subsequence_candidates_many, subsequence_candidates
from .keyword_training import FamilyClassifier, augment_audio


@dataclass(frozen=True)
class KeywordEvent:
    start_s: float
    end_s: float
    observed_until_s: float
    prediction: Prediction

    def to_dict(self) -> dict:
        return {'start_s': self.start_s, 'end_s': self.end_s,
                'observed_until_s': self.observed_until_s, **self.prediction.to_dict()}


class KeywordSpotter:
    """Synchronous bounded stream processor; call on the audio worker, not its callback.

    No microphone, TTS, request or UI access. pause/reset during TTS, enrollment
    and confirmation remains the caller's responsibility. Never bypass confirmation.
    Scores/rejection are experimental: word-only calibration does not account for
    the many opportunities for false acceptance in a continuous stream.
    """
    def __init__(self, references: PrototypeClassifier, *, max_candidates: int = 2,
                 stride_s: float = .75, window_s: float = 5.,
                 alignment_stride: int = 3, feature_weights: tuple[float,float,float] = (1.,.5,.25),
                 parent_ids: list[str] | None = None, refine_boundaries: bool = True):
        if references.feature_config.normalization != 'none':
            raise ValueError('keyword spotting requires new raw-MFCC enrollment, not utterance-CMVN templates')
        if len(references.classes) < 2 or not references.seqs:
            raise ValueError('enroll at least two distinct keywords')
        if not 1 <= max_candidates <= 8 or not .25 <= stride_s <= 2 or not 1 <= window_s <= 5:
            raise ValueError('invalid bounded keyword scan settings')
        if not isinstance(alignment_stride,int) or not 1<=alignment_stride<=4:
            raise ValueError('alignment stride must be 1–4')
        weights=np.asarray(feature_weights,dtype=float)
        if weights.shape!=(3,) or not np.isfinite(weights).all() or np.any(weights<=0) or np.any(weights>2):
            raise ValueError('invalid MFCC/delta feature weights')
        self.refine_boundaries=bool(refine_boundaries)
        self.alignment_stride=alignment_stride
        self.feature_weights=tuple(float(w) for w in weights)
        self._weights=np.repeat(weights,references.feature_config.n_mfcc)
        self.parent_ids=list(parent_ids) if parent_ids is not None else [f'real_{i}' for i in range(len(references.seqs))]
        if len(self.parent_ids)!=len(references.seqs) or any(not isinstance(p,str) or not p for p in self.parent_ids):
            raise ValueError('invalid source-family metadata')
        families={}
        for label,parent in zip(references.labels,self.parent_ids):
            if parent in families and families[parent]!=label:raise ValueError('source family crosses intents')
            families[parent]=label
        self.enrollment_info={'source':'imported reference features'}
        self.references = references
        self.feature_config = references.feature_config
        self.max_candidates = max_candidates
        self.stride_samples = int(16000*stride_s)
        self.window_samples = int(16000*window_s)
        # Fitted only on enrollment; reused unchanged for every stream window.
        first=[self.parent_ids.index(p) for p in dict.fromkeys(self.parent_ids)]
        pooled = np.concatenate([references.seqs[i] for i in first]).astype(np.float64)
        self.mean = pooled.mean(axis=0)
        self.scale = np.maximum(pooled.std(axis=0), self.feature_config.variance_floor)
        self.classifier = FamilyClassifier(self.parent_ids,k=references.k, band=references.band,
                                              feature_config=self.feature_config)
        self.classifier.margin = references.margin
        self.classifier.threshold = references.threshold
        self._full_templates=[self.normalize(seq) for seq in references.seqs]
        for label, seq in zip(references.labels, self._full_templates):
            self.classifier.add(label, seq[::self.alignment_stride])
        self.classifier.calibrate()
        self.reset()

    def normalize(self, features: np.ndarray) -> np.ndarray:
        return (((features-self.mean)/self.scale)*self._weights).astype(np.float32)

    @staticmethod
    def audio(samples: np.ndarray) -> np.ndarray:
        samples = np.asarray(samples, dtype=np.float32)
        if (samples.ndim != 1 or not 4800 <= len(samples) <= 80000 or not np.isfinite(samples).all()
                or np.max(np.abs(samples), initial=0) > 1.001):
            raise ValueError('expected 0.3–5 s finite 16 kHz mono audio in [-1,1]')
        if np.mean(np.abs(samples) >= .999) > .05:
            raise ValueError('recording is clipped')
        samples = samples-samples.mean()
        if np.sqrt(np.mean(samples.astype(np.float64)**2)) < .00003:
            raise ValueError('recording is silent or too quiet')
        return samples

    @classmethod
    def prepare_enrollment(cls, clip: np.ndarray, trim_endpoints: bool = True) -> np.ndarray:
        audio=cls.audio(clip)
        if trim_endpoints:
            audio=cls.audio(trim_silence(audio,16000,pad_ms=180))
        return audio

    @classmethod
    def enroll(cls, recordings: dict[str, list[np.ndarray]], *,
               trim_endpoints: bool = True, synthetic_per_intent: int = 0,
               seed: int = 0, allow_few_shot: bool = False,
               augmentation_policy: str = 'balanced20', **kwargs) -> KeywordSpotter:
        if augmentation_policy not in ('mild35','balanced20'):raise ValueError('invalid augmentation policy')
        if not 0<=synthetic_per_intent<=5:raise ValueError('synthetic variants must be 0–5 per intent')
        if len(recordings)<2 or any(not clips for clips in recordings.values()):
            raise ValueError('enroll at least two keywords with nonempty recordings')
        if not allow_few_shot and any(len(clips)<5 for clips in recordings.values()):
            raise ValueError('record at least five independent takes per keyword; few-shot is evaluation-only')
        references = PrototypeClassifier(feature_config=FeatureConfig(normalization='none'))
        parents=[]
        for label, clips in recordings.items():
            prepared=[]
            for index,clip in enumerate(clips):
                audio = cls.prepare_enrollment(clip,trim_endpoints)
                references.add(label, mfcc(audio, config=references.feature_config))
                prepared.append(audio);parents.append(f'{label}:{index}')
            if len(clips)+synthetic_per_intent>10:raise ValueError('maximum ten references per intent including variants')
            for index in range(synthetic_per_intent):
                parent=index%len(prepared)
                kind=(('gain','speed','noise')[index%3] if augmentation_policy=='mild35'
                      else ('noise','noise','gain','speed','noise')[index])
                snr=35 if augmentation_policy=='mild35' else 20
                try:
                    try:variant=augment_audio(prepared[parent],kind,seed+index,snr_db=snr)
                    except ValueError:variant=augment_audio(prepared[parent],'noise',seed+index,snr_db=snr)
                    references.add(label,mfcc(cls.audio(variant),config=references.feature_config))
                except ValueError:
                    # Optional copies must not invalidate good quiet human recordings.
                    continue
                parents.append(f'{label}:{parent}')
        model=cls(references,parent_ids=parents,**kwargs)
        model.enrollment_info={'requested_synthetic_per_intent':synthetic_per_intent,'augmentation_policy':augmentation_policy,
                               'seed':seed,'few_shot_exception':allow_few_shot,'minimum_real_takes':5}
        return model

    def scan(self, audio: np.ndarray, *, offset_s: float = 0.) -> list[KeywordEvent]:
        """Find up to max_candidates nonoverlapping proposals in one <=5 s window.

        All intents are rescored on the SAME proposed span, so competing words
        at different positions do not incorrectly count as an ambiguous event.
        Returned events include rejections for evaluation; only accepted=True
        is a recognition candidate, and never a caregiver request.
        """
        started = time.perf_counter()
        try:
            samples = self.audio(audio)
        except (ValueError,TypeError):
            return []
        full_features = self.normalize(mfcc(samples, config=self.feature_config))
        features = full_features[::self.alignment_stride]
        proposals = []
        for template_index,matches in enumerate(subsequence_candidates_many(self.classifier.seqs,features,max_matches=self.max_candidates)):
            proposals.extend((found,template_index) for found in matches)
        selected = []
        for found,template_index in sorted(proposals, key=lambda p: p[0].distance):
            if any(max(0, min(found.end,p.end)-max(found.start,p.start))
                   / min(found.end-found.start,p.end-p.start) > .5 for p,_ in selected):
                continue
            selected.append((found,template_index))
            if len(selected) >= self.max_candidates:
                break
        raw_hop = int(16000*self.feature_config.hop_length_ms/1000)
        win = int(16000*self.feature_config.window_length_ms/1000)
        events = []
        for found,template_index in selected:
            first,last=found.start*self.alignment_stride,min(len(full_features),found.end*self.alignment_stride)
            if self.refine_boundaries and self.alignment_stride>2:
                # A cheap coarse proposal must not chop off a consonant/word edge.
                # Refine only its bounded neighborhood, using one originating template.
                padding=max(15,round(len(self._full_templates[template_index])*.25))
                lo,hi=max(0,first-padding),min(len(full_features),last+padding)
                refined=subsequence_candidates(self._full_templates[template_index][::2],
                                                full_features[lo:hi:2],max_matches=1)
                if refined:
                    first=lo+refined[0].start*2
                    last=min(len(full_features),lo+refined[0].end*2)
                # MFCC windows/derivatives see neighboring phonemes. Preserve 40 ms
                # before the refined span and 20 ms after its last window, then re-extract.
                first=max(0,first-4);last=min(len(full_features),last+2)
            start,end=first*raw_hop,min(len(samples),(last-1)*raw_hop+win)
            try:
                self.audio(samples[start:end])
            except ValueError:
                continue
            if self.refine_boundaries and self.alignment_stride>2:
                raw=np.asarray(audio,dtype=np.float32)[start:end]
                settings=(self.classifier.threshold,self.classifier.margin,self.classifier.band,self.classifier.k,
                          tuple(sorted(self.classifier.per_intent_thresholds.items())))
                if settings!=self._cache_settings:
                    self._score_cache.clear();self._cache_settings=settings
                key=hashlib.blake2b(raw.tobytes(),digest_size=16).digest()
                cached=self._score_cache.pop(key,None)
                if cached is None:
                    try:crop=self.audio(raw)
                    except ValueError:continue
                    query=self.normalize(mfcc(crop,config=self.feature_config))[::self.alignment_stride]
                    cached=self.classifier.predict(query)
                self._score_cache[key]=cached
                if len(self._score_cache)>64:self._score_cache.popitem(last=False)
                prediction=replace(cached,scores=dict(cached.scores))
            else:
                prediction = self.classifier.predict(full_features[first:last:self.alignment_stride])
            events.append(KeywordEvent(offset_s+start/16000, offset_s+end/16000,
                                       offset_s+len(samples)/16000, prediction))
        if self.refine_boundaries and self.alignment_stride>2:
            unique=[]
            for event in sorted(events,key=lambda e:(not e.prediction.accepted,e.prediction.distance)):
                if any(max(0,min(event.end_s,p.end_s)-max(event.start_s,p.start_s))
                       /min(event.end_s-event.start_s,p.end_s-p.start_s)>.5 for p in unique):continue
                unique.append(event)
            events=unique
        elapsed = (time.perf_counter()-started)*1000
        for event in events:
            event.prediction.latency_ms = elapsed  # full scan processing, not one template cost
        return sorted(events, key=lambda e:e.start_s)

    def reset(self) -> None:
        """Discard buffered audio and detection state; use when pausing/reloading."""
        self._score_cache: OrderedDict[bytes,Prediction]=OrderedDict()
        self._cache_settings=None
        self._buffer = np.empty(0, dtype=np.float32)
        self._samples_seen = 0
        self._since_scan = 0
        self._emitted: list[tuple[float, float]] = []

    def feed(self, chunk: np.ndarray) -> list[KeywordEvent]:
        """Feed <=1 second at a time; keeps <=5 seconds, no unbounded work queue.

        Processing is synchronous and may exceed real time on the UNO Q. Measure
        real-time factor before connecting this experimental path to a live mic.
        """
        try:
            chunk = np.asarray(chunk, dtype=np.float32)
        except (TypeError,ValueError) as exc:
            self.reset()
            raise ValueError('feed needs numeric mono audio; stream state was reset') from exc
        if (chunk.ndim != 1 or not 0 < len(chunk) <= 16000 or not np.isfinite(chunk).all()
                or np.max(np.abs(chunk), initial=0) > 1.001):
            self.reset()
            raise ValueError('feed needs 1 sample–1 second of finite mono audio')
        result=[]
        consumed=0
        while consumed<len(chunk):
            # Honor audio-clock scan boundaries even when a caller supplies a whole
            # second at once. The initial 0.3 s is needed for valid MFCC input.
            until_scan=max(self.stride_samples-self._since_scan,4800-len(self._buffer),1)
            count=min(len(chunk)-consumed,until_scan)
            part=chunk[consumed:consumed+count]
            consumed+=count
            self._buffer=np.concatenate((self._buffer,part))[-self.window_samples:]
            self._samples_seen+=count
            self._since_scan+=count
            if self._since_scan<self.stride_samples or len(self._buffer)<4800:
                continue
            self._since_scan%=self.stride_samples
            offset=(self._samples_seen-len(self._buffer))/16000
            self._emitted=[(a,b) for a,b in self._emitted if b>offset]
            for event in self.scan(self._buffer,offset_s=offset):
                if event.prediction.accepted:
                    if any(max(0,min(event.end_s,b)-max(event.start_s,a))
                           /min(event.end_s-event.start_s,b-a)>.5 for a,b in self._emitted):
                        continue
                    self._emitted.append((event.start_s,event.end_s))
                result.append(event)
        return result

    def save(self, directory: Path) -> None:
        """Feature-only keyword profile; separate files from production active profiles."""
        directory = Path(directory)
        self.references.save(directory/'references')
        meta = {'version': 2, 'kind': 'experimental_keyword_spotter',
                'references_metadata_sha256': hashlib.sha256((directory/'references/metadata.json').read_bytes()).hexdigest(),
                'max_candidates': self.max_candidates, 'stride_s': self.stride_samples/16000,
                'window_s': self.window_samples/16000,'alignment_stride':self.alignment_stride,
                'feature_weights':self.feature_weights,'parent_ids':self.parent_ids,
                'calibration':self.classifier.calibration,'enrollment_info':self.enrollment_info,
                'refine_boundaries':self.refine_boundaries}
        temporary = directory/'keyword.tmp'
        temporary.write_text(json.dumps(meta, indent=2, allow_nan=False))
        temporary.replace(directory/'keyword.json')

    @classmethod
    def load(cls, directory: Path) -> KeywordSpotter:
        directory = Path(directory)
        try:
            meta = json.loads((directory/'keyword.json').read_text())
            if meta['version'] not in (1,2) or meta['kind'] != 'experimental_keyword_spotter':
                raise ValueError('unsupported keyword profile')
            digest = hashlib.sha256((directory/'references/metadata.json').read_bytes()).hexdigest()
            if digest != meta['references_metadata_sha256']:
                raise ValueError('incomplete keyword profile')
            references = PrototypeClassifier.load(directory/'references')
            model=cls(references, max_candidates=meta['max_candidates'],
                       stride_s=meta['stride_s'], window_s=meta['window_s'],
                       alignment_stride=meta.get('alignment_stride',1),
                       feature_weights=tuple(meta.get('feature_weights',(1.,1.,1.))),
                       parent_ids=meta.get('parent_ids'),refine_boundaries=meta.get('refine_boundaries',False) if meta['version']>=2 else False)
            model.enrollment_info=meta.get('enrollment_info',model.enrollment_info)
            return model
        except (KeyError, TypeError) as exc:
            raise ValueError('invalid keyword profile') from exc
