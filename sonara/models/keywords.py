"""Experimental personalized keywords inside phrases, without a controller side effect.

Uses enrollment-fitted shared MFCC scaling, free-endpoint DTW proposals and
whole-span all-intent rescoring. Existing utterance-CMVN profiles cannot be reused.
A separate keyword profile and continuous-speech negative validation are required.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..audio.vad import trim_silence
from .classifier import Prediction, PrototypeClassifier
from .features import FeatureConfig, mfcc
from .subsequence import subsequence_candidates


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
    def __init__(self, references: PrototypeClassifier, *, max_candidates: int = 3,
                 stride_s: float = .5, window_s: float = 5.):
        if references.feature_config.normalization != 'none':
            raise ValueError('keyword spotting requires new raw-MFCC enrollment, not utterance-CMVN templates')
        if len(references.classes) < 2 or not references.seqs:
            raise ValueError('enroll at least two distinct keywords')
        if not 1 <= max_candidates <= 8 or not .25 <= stride_s <= 2 or not 1 <= window_s <= 5:
            raise ValueError('invalid bounded keyword scan settings')
        self.references = references
        self.feature_config = references.feature_config
        self.max_candidates = max_candidates
        self.stride_samples = int(16000*stride_s)
        self.window_samples = int(16000*window_s)
        # Fitted only on enrollment; reused unchanged for every stream window.
        pooled = np.concatenate(references.seqs).astype(np.float64)
        self.mean = pooled.mean(axis=0)
        self.scale = np.maximum(pooled.std(axis=0), self.feature_config.variance_floor)
        self.classifier = PrototypeClassifier(k=references.k, band=references.band,
                                              feature_config=self.feature_config)
        self.classifier.margin = references.margin
        self.classifier.threshold = references.threshold
        for label, seq in zip(references.labels, references.seqs):
            self.classifier.add(label, self.normalize(seq))
        self.classifier.calibrate()
        self.reset()

    def normalize(self, features: np.ndarray) -> np.ndarray:
        return ((features-self.mean)/self.scale).astype(np.float32)

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
    def enroll(cls, recordings: dict[str, list[np.ndarray]], *,
               trim_endpoints: bool = True, **kwargs) -> KeywordSpotter:
        references = PrototypeClassifier(feature_config=FeatureConfig(normalization='none'))
        for label, clips in recordings.items():
            for clip in clips:
                audio = cls.audio(clip)
                if trim_endpoints:
                    # Preserve internal pauses and 180 ms padding. Manual word boundaries
                    # remain available with trim_endpoints=False for atypical quiet speech.
                    audio = cls.audio(trim_silence(audio, 16000, pad_ms=180))
                references.add(label, mfcc(audio, config=references.feature_config))
        return cls(references, **kwargs)

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
        except ValueError:
            return []
        features = self.normalize(mfcc(samples, config=self.feature_config))
        proposals = []
        for template in self.classifier.seqs:
            proposals.extend(subsequence_candidates(template, features, max_matches=self.max_candidates))
        selected = []
        for found in sorted(proposals, key=lambda p: p.distance):
            if any(max(0, min(found.end,p.end)-max(found.start,p.start))
                   / min(found.end-found.start,p.end-p.start) > .5 for p in selected):
                continue
            selected.append(found)
            if len(selected) >= self.max_candidates:
                break
        hop = int(16000*self.feature_config.hop_length_ms/1000)
        win = int(16000*self.feature_config.window_length_ms/1000)
        events = []
        for found in selected:
            start, end = found.start*hop, min(len(samples), (found.end-1)*hop+win)
            try:
                self.audio(samples[start:end])
            except ValueError:
                continue
            prediction = self.classifier.predict(features[found.start:found.end])
            events.append(KeywordEvent(offset_s+start/16000, offset_s+end/16000,
                                       offset_s+len(samples)/16000, prediction))
        elapsed = (time.perf_counter()-started)*1000
        for event in events:
            event.prediction.latency_ms = elapsed  # full scan processing, not one template cost
        return sorted(events, key=lambda e:e.start_s)

    def reset(self) -> None:
        """Discard buffered audio and detection state; use when pausing/reloading."""
        self._buffer = np.empty(0, dtype=np.float32)
        self._samples_seen = 0
        self._since_scan = 0
        self._emitted: list[tuple[float, float]] = []

    def feed(self, chunk: np.ndarray) -> list[KeywordEvent]:
        """Feed <=1 second at a time; keeps <=5 seconds, no unbounded work queue.

        Processing is synchronous and may exceed real time on the UNO Q. Measure
        real-time factor before connecting this experimental path to a live mic.
        """
        chunk = np.asarray(chunk, dtype=np.float32)
        if (chunk.ndim != 1 or not 0 < len(chunk) <= 16000 or not np.isfinite(chunk).all()
                or np.max(np.abs(chunk), initial=0) > 1.001):
            self.reset()
            raise ValueError('feed needs 1 sample–1 second of finite mono audio')
        self._buffer = np.concatenate((self._buffer, chunk))[-self.window_samples:]
        self._samples_seen += len(chunk)
        self._since_scan += len(chunk)
        if self._since_scan < self.stride_samples or len(self._buffer) < 4800:
            return []
        self._since_scan %= self.stride_samples
        offset = (self._samples_seen-len(self._buffer))/16000
        self._emitted = [(a,b) for a,b in self._emitted if b > offset]
        events = self.scan(self._buffer, offset_s=offset)
        result = []
        for event in events:
            if event.prediction.accepted:
                if any(max(0,min(event.end_s,b)-max(event.start_s,a))
                       / min(event.end_s-event.start_s,b-a) > .5 for a,b in self._emitted):
                    continue
                self._emitted.append((event.start_s,event.end_s))
            result.append(event)
        return result

    def save(self, directory: Path) -> None:
        """Feature-only keyword profile; separate files from production active profiles."""
        directory = Path(directory)
        self.references.save(directory/'references')
        meta = {'version': 1, 'kind': 'experimental_keyword_spotter',
                'references_metadata_sha256': hashlib.sha256((directory/'references/metadata.json').read_bytes()).hexdigest(),
                'max_candidates': self.max_candidates, 'stride_s': self.stride_samples/16000,
                'window_s': self.window_samples/16000}
        temporary = directory/'keyword.tmp'
        temporary.write_text(json.dumps(meta, indent=2, allow_nan=False))
        temporary.replace(directory/'keyword.json')

    @classmethod
    def load(cls, directory: Path) -> KeywordSpotter:
        directory = Path(directory)
        try:
            meta = json.loads((directory/'keyword.json').read_text())
            if meta['version'] != 1 or meta['kind'] != 'experimental_keyword_spotter':
                raise ValueError('unsupported keyword profile')
            digest = hashlib.sha256((directory/'references/metadata.json').read_bytes()).hexdigest()
            if digest != meta['references_metadata_sha256']:
                raise ValueError('incomplete keyword profile')
            references = PrototypeClassifier.load(directory/'references')
            return cls(references, max_candidates=meta['max_candidates'],
                       stride_s=meta['stride_s'], window_s=meta['window_s'])
        except (KeyError, TypeError) as exc:
            raise ValueError('invalid keyword profile') from exc
