"""Bounded subsequence DTW for experimental keyword localization.

Free stream endpoints differ from whole-utterance DTW. Endpoint duration bounds
reject collapsed/overlong alignments; they do not impose a Sakoe–Chiba diagonal.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SubsequenceMatch:
    distance: float
    start: int
    end: int  # exclusive stream frame index
    path_length: int


def subsequence_candidates(template: np.ndarray, stream: np.ndarray,
                    duration_ratio: tuple[float, float] = (.5, 2.),
                    step_penalty: float = .05, max_matches: int = 3) -> list[SubsequenceMatch]:
    """Lowest normalized endpoint cost on the minimum accumulated-cost paths.

    D(0,j)=0 permits starting anywhere; D(i,0)=inf for i>0. Ties prefer
    diagonal, vertical, horizontal. Non-diagonal steps pay a small penalty.
    Only the selected path per cell is retained; a rejected duration does not
    search alternate paths to that endpoint. O(stream frames) workspace.
    Inputs must already share a feature normalization fitted on enrollment only.
    """
    if not 1 <= max_matches <= 8:
        raise ValueError('subsequence candidate limit must be 1–8')
    low, high = duration_ratio
    if not 0 < low <= high <= 3 or not np.isfinite(step_penalty) or step_penalty < 0:
        raise ValueError('invalid subsequence duration bounds or step penalty')
    a, b = np.asarray(template, dtype=np.float64), np.asarray(stream, dtype=np.float64)
    if (a.ndim != 2 or b.ndim != 2 or not 1 <= len(a) <= 600 or not 1 <= len(b) <= 600
            or not 1 <= a.shape[1] <= 128 or a.shape[1] != b.shape[1]
            or not np.isfinite(a).all() or not np.isfinite(b).all()):
        return []
    n, m = len(a), len(b)
    previous = np.zeros(m+1)
    lengths = np.zeros(m+1, dtype=np.int32)
    starts = np.arange(m+1, dtype=np.int32)
    columns = np.arange(m)
    for i in range(1, n+1):
        diff = b-a[i-1]
        costs = np.sqrt(np.einsum('ij,ij->i', diff, diff, optimize=False)/a.shape[1])
        diagonal, vertical = previous[:-1], previous[1:] + step_penalty
        choose_diagonal = diagonal <= vertical
        incoming = np.minimum(diagonal, vertical)
        incoming_lengths = np.where(choose_diagonal, lengths[:-1], lengths[1:])
        incoming_starts = np.where(choose_diagonal, starts[:-1], starts[1:])
        # Horizontal recurrence: row[j] = cost[j] + min(incoming[j], row[j-1]+penalty).
        cumulative = np.cumsum(costs + step_penalty)
        offsets = incoming - step_penalty - np.r_[0., cumulative[:-1]]
        minima = np.minimum.accumulate(offsets)
        origins = np.maximum.accumulate(np.where(offsets <= minima, columns, 0))
        previous = np.r_[np.inf, cumulative + minima]
        lengths = np.r_[0, incoming_lengths[origins] + columns-origins+1]
        starts = np.r_[0, incoming_starts[origins]]
    durations = np.arange(1, m+1)-starts[1:]
    valid = (durations >= max(1, int(np.ceil(n*low)))) & (durations <= int(np.floor(n*high)))
    normalized = np.divide(previous[1:], lengths[1:], out=np.full(m, np.inf), where=lengths[1:] > 0)
    normalized[~valid] = np.inf
    matches = []
    for endpoint in np.argsort(normalized, kind='stable'):
        if not np.isfinite(normalized[endpoint]):
            break
        end = int(endpoint)+1
        found = SubsequenceMatch(float(max(0., normalized[endpoint])), int(starts[end]), end, int(lengths[end]))
        if any(max(0, min(found.end,p.end)-max(found.start,p.start))
               / min(found.end-found.start,p.end-p.start) > .5 for p in matches):
            continue
        matches.append(found)
        if len(matches) >= max_matches:
            break
    return matches


def subsequence_dtw(template: np.ndarray, stream: np.ndarray,
                    duration_ratio: tuple[float, float] = (.5, 2.),
                    step_penalty: float = .05) -> SubsequenceMatch | None:
    """Return the single best bounded subsequence alignment, or None."""
    matches = subsequence_candidates(template, stream, duration_ratio, step_penalty, max_matches=1)
    return matches[0] if matches else None


def subsequence_candidates_many(templates: list[np.ndarray], stream: np.ndarray,
                                duration_ratio: tuple[float, float] = (.5, 2.),
                                step_penalty: float = .05, max_matches: int = 3,
                                batch_size: int = 16) -> list[list[SubsequenceMatch]]:
    """Exact scalar recurrence in bounded batches, sharing the Python row loop.

    This optimization alone does not change the frame rate, distance or alignment.
    Each reference retains its own length and free endpoints. <=100 references,
    <=600 frames, <=128 dimensions and <=16 references per batch.
    """
    low, high = duration_ratio
    if (not 0 < low <= high <= 3 or not np.isfinite(step_penalty) or step_penalty < 0
            or not 1 <= max_matches <= 8 or not 1 <= batch_size <= 16 or len(templates)>100):
        raise ValueError('invalid batched subsequence settings')
    b=np.asarray(stream,dtype=np.float64)
    output=[[] for _ in templates]
    if (b.ndim!=2 or not 1<=len(b)<=600 or not 1<=b.shape[1]<=128 or not np.isfinite(b).all()):
        return output
    valid=[]
    for index,a in enumerate(templates):
        a=np.asarray(a,dtype=np.float64)
        if a.ndim==2 and 1<=len(a)<=600 and a.shape[1]==b.shape[1] and np.isfinite(a).all():
            valid.append((index,a))
    m,dimensions=b.shape
    columns=np.arange(m)
    for first in range(0,len(valid),batch_size):
        batch=valid[first:first+batch_size];count=len(batch)
        sizes=np.array([len(a) for _,a in batch],dtype=np.int32)
        data=np.zeros((count,int(sizes.max()),dimensions))
        for k,(_,a) in enumerate(batch):data[k,:len(a)]=a
        previous=np.zeros((count,m+1));lengths=np.zeros((count,m+1),np.int32)
        starts=np.broadcast_to(np.arange(m+1),(count,m+1)).copy()
        for i in range(1,int(sizes.max())+1):
            diff=b[None,:,:]-data[:,i-1,None,:]
            costs=np.sqrt(np.einsum('bmd,bmd->bm',diff,diff,optimize=False)/dimensions)
            diagonal,vertical=previous[:,:-1],previous[:,1:]+step_penalty
            choose=diagonal<=vertical
            incoming=np.minimum(diagonal,vertical)
            incoming_lengths=np.where(choose,lengths[:,:-1],lengths[:,1:])
            incoming_starts=np.where(choose,starts[:,:-1],starts[:,1:])
            cumulative=np.cumsum(costs+step_penalty,axis=1)
            offsets=incoming-step_penalty
            offsets[:,1:]-=cumulative[:,:-1]
            minima=np.minimum.accumulate(offsets,axis=1)
            origins=np.maximum.accumulate(np.where(offsets<=minima,columns[None,:],0),axis=1)
            previous[:,0]=np.inf;previous[:,1:]=cumulative+minima
            lengths[:,0]=0
            lengths[:,1:]=np.take_along_axis(incoming_lengths,origins,axis=1)+columns[None,:]-origins+1
            starts[:,0]=0
            starts[:,1:]=np.take_along_axis(incoming_starts,origins,axis=1)
            for k in np.flatnonzero(sizes==i):
                durations=np.arange(1,m+1)-starts[k,1:]
                allowed=(durations>=max(1,int(np.ceil(i*low)))) & (durations<=int(np.floor(i*high)))
                normalized=np.divide(previous[k,1:],lengths[k,1:],out=np.full(m,np.inf),where=lengths[k,1:]>0)
                normalized[~allowed]=np.inf
                matches=[]
                for endpoint in np.argsort(normalized,kind='stable'):
                    if not np.isfinite(normalized[endpoint]):break
                    end=int(endpoint)+1
                    found=SubsequenceMatch(float(max(0.,normalized[endpoint])),int(starts[k,end]),end,int(lengths[k,end]))
                    if any(max(0,min(found.end,p.end)-max(found.start,p.start))
                           /min(found.end-found.start,p.end-p.start)>.5 for p in matches):continue
                    matches.append(found)
                    if len(matches)>=max_matches:break
                output[batch[k][0]]=matches
    return output
