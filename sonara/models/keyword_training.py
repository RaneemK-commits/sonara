"""Optional synthetic enrollment variants with source-family-aware calibration."""
from __future__ import annotations

import numpy as np

from .classifier import PrototypeClassifier
from .dtw import dtw_distances


def augment_audio(audio: np.ndarray, kind: str, seed: int, snr_db: float = 35.) -> np.ndarray:
    """Gentle test augmentation, not new human takes or simulated disability.

    Resampling changes speed AND pitch slightly; no neural/vocoder dependency.
    Reject an invalid duration rather than cropping a vocalization to make it fit.
    """
    a=np.asarray(audio,dtype=np.float32)
    if a.ndim!=1 or not 4800<=len(a)<=80000 or not np.isfinite(a).all():
        raise ValueError('invalid augmentation source')
    rng=np.random.default_rng(seed)
    if kind=='gain':
        out=a*(.85 if seed%2==0 else 1.12)
    elif kind=='speed':
        ratio=.95 if seed%2==0 else 1.05
        size=round(len(a)/ratio)
        if not 4800<=size<=80000:raise ValueError('augmentation would exceed recording bounds')
        out=np.interp(np.linspace(0,len(a)-1,size),np.arange(len(a)),a)
    elif kind=='noise':
        noise=rng.standard_normal(len(a))
        if not 10<=snr_db<=60:raise ValueError('augmentation SNR must be 10–60 dB')
        noise*=np.sqrt(np.mean(a.astype(np.float64)**2))/(10**(snr_db/20))/max(np.sqrt(np.mean(noise**2)),1e-12)
        out=a+noise
    else:raise ValueError('unknown augmentation kind')
    out*=min(1.,.95/max(float(np.max(np.abs(out),initial=0)),1e-12))
    return np.asarray(out,dtype=np.float32)


class FamilyClassifier(PrototypeClassifier):
    """Mean of nearest independent source families; leave a whole family out.

    Synthetic siblings cannot vote twice or calibrate against their own parent.
    The first reference in a family must be its real, unaugmented source.
    """
    def __init__(self, families: list[str], **kwargs):
        super().__init__(**kwargs)
        self.families=families

    def scores(self, seq: np.ndarray, exclude: int | None=None) -> dict[str,float]:
        if len(self.families)!=len(self.seqs):raise ValueError('reference family mismatch')
        excluded=self.families[exclude] if exclude is not None else None
        selected=[i for i in range(len(self.seqs)) if self.families[i]!=excluded]
        distances=dtw_distances(seq,[self.seqs[i] for i in selected],band=self.band)
        per={}
        for i,distance in zip(selected,distances):
            group=per.setdefault(self.labels[i],{})
            family=self.families[i]
            group[family]=min(group.get(family,float('inf')),distance)
        return {label:float(np.mean(sorted(groups.values())[:self.k])) for label,groups in per.items()}

    def calibrate(self, slack: float=1.15, unknown: list[np.ndarray] | None=None) -> float:
        first=list(dict.fromkeys(self.families))
        indices=[self.families.index(family) for family in first]
        pos={c:[] for c in self.classes};neg={c:[] for c in self.classes};gaps={c:[] for c in self.classes}
        for i in indices:
            label=self.labels[i];scores=self.scores(self.seqs[i],exclude=i)
            for c,d in scores.items():(pos if c==label else neg)[c].append(d)
            others=[d for c,d in scores.items() if c!=label]
            if label in scores and others:gaps[label].append(min(others)-scores[label])
        for seq in unknown or []:
            for c,d in self.scores(seq).items():neg[c].append(d)
        detail={};self.per_intent_thresholds={}
        for c in self.classes:
            p90=float(np.percentile(pos[c],90)) if pos[c] else None
            n10=float(np.percentile(neg[c],10)) if neg[c] else None
            gap=float(np.percentile(gaps[c],10)) if gaps[c] else None
            limit=min(self.threshold,max(.05,p90*slack) if p90 is not None else .6,n10*.8 if n10 is not None else .6)
            self.per_intent_thresholds[c]=max(0.,limit)
            count=sum(self.labels[i]==c for i in indices)
            status=('needs_five_independent_recordings' if count<5 else
                    'overlapping_intents' if n10 is None or p90 is None or p90>=n10 else
                    'distance_threshold_rejects_enrollment' if p90>=limit else
                    'margin_not_separated' if gap is None or gap<self.margin else 'separated_on_enrollment_only')
            detail[c]={'independent_recordings':count,'template_count':self.labels.count(c),
                       'synthetic_variants':self.labels.count(c)-count,'positive_loo':len(pos[c]),
                       'negative':len(neg[c]),'positive_p90':p90,'negative_p10':n10,
                       'loo_gap_p10':gap,'threshold':limit,'status':status,
                       'requires_more_recordings':status!='separated_on_enrollment_only'}
        self.calibration={'method':'leave-one-source-family-out; siblings excluded; family-min scores',
                          'requires_more_recordings':any(d['requires_more_recordings'] for d in detail.values()),
                          'intents':detail,'warning':'Synthetic variants are not independent recordings; word calibration does not validate continuous false acceptance.'}
        return self.threshold
