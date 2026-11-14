"""Explicitly enabled native DTW; NumPy remains the portable default."""
from __future__ import annotations
import ctypes
from functools import lru_cache
import os
import numpy as np


class NativeDTW:
    def __init__(self, path: str):
        self.library=ctypes.CDLL(path)
        self.library.sonara_dtw_abi.restype=ctypes.c_int
        self.library.sonara_dtw_abi.argtypes=[]
        if self.library.sonara_dtw_abi()!=1:raise ValueError('Unsupported native DTW ABI')
        self.function=self.library.sonara_dtw
        self.function.argtypes=[ctypes.POINTER(ctypes.c_double),ctypes.c_int,
                                ctypes.POINTER(ctypes.c_double),ctypes.c_int,ctypes.c_int,ctypes.c_double]
        self.function.restype=ctypes.c_double

    def distances(self, query: np.ndarray, templates: list[np.ndarray], band: float=.2) -> list[float]:
        if not np.isfinite(band) or not 0<=band<=1:raise ValueError('Invalid DTW band')
        if len(templates)>100:raise ValueError('Native batch exceeds reference bound')
        query=np.ascontiguousarray(query,dtype=np.float64)
        valid=lambda a:a.ndim==2 and 1<=len(a)<=600 and 1<=a.shape[1]<=128 and np.isfinite(a).all()
        if not valid(query):return [float('inf')]*len(templates)
        pointer=ctypes.POINTER(ctypes.c_double)
        result=[]
        for template in templates:
            template=np.ascontiguousarray(template,dtype=np.float64)
            if not valid(template) or template.shape[1]!=query.shape[1]:
                result.append(float('inf'));continue
            result.append(self.function(query.ctypes.data_as(pointer),len(query),
                                        template.ctypes.data_as(pointer),len(template),query.shape[1],band))
        return result


@lru_cache(maxsize=4)
def load_engine(path: str) -> NativeDTW:
    return NativeDTW(path)


def engine_from_env() -> NativeDTW | None:
    path=os.environ.get('SONARA_DTW_LIBRARY')
    return load_engine(path) if path else None
