"""Single production acoustic frontend."""
from __future__ import annotations
import numpy as np
from .features import FeatureConfig, mfcc


class MFCCEmbedder:
    name = "mfcc"

    def __init__(self, config: FeatureConfig | None = None):
        self.config = config or FeatureConfig()

    def __call__(self, audio: np.ndarray) -> np.ndarray:
        return mfcc(audio, config=self.config)
