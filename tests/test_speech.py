import numpy as np
import pytest

from sonara.audio.vad import StreamingVAD, trim_silence
from sonara.models.classifier import PrototypeClassifier
from sonara.models.dtw import dtw_distance
from sonara.models.features import mfcc

SR = 16000


def tone(freqs, dur=0.6, sr=SR, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(int(dur * sr)) / sr
    segs = [np.sin(2 * np.pi * f * t[: len(t) // len(freqs)]) for f in freqs]
    return (0.3 * np.concatenate(segs) + 0.01 * rng.standard_normal(sum(map(len, segs)))).astype(np.float32)


def test_dtw_identity_and_order():
    a = np.random.default_rng(0).standard_normal((30, 8)).astype(np.float32)
    assert dtw_distance(a, a) == pytest.approx(0, abs=1e-5)
    b = np.repeat(a, 2, axis=0)  # time-stretched copy should stay close
    c = np.random.default_rng(1).standard_normal((30, 8)).astype(np.float32)
    assert dtw_distance(a, b) < dtw_distance(a, c)


def test_mfcc_shape():
    f = mfcc(tone([300]), SR)
    assert f.ndim == 2 and f.shape[1] == 39 and f.shape[0] > 50


def test_trim_and_vad():
    sig = np.concatenate([np.zeros(8000), tone([400]), np.zeros(8000)]).astype(np.float32)
    trimmed = trim_silence(sig, SR)
    assert len(tone([400])) <= len(trimmed) < len(sig)
    vad = StreamingVAD(SR, 30, silence_end_ms=300)
    blk = int(SR * 0.03)
    events = [vad.update(sig[i:i + blk]) for i in range(0, len(sig) - blk, blk)]
    assert "start" in events and "end" in events


def test_classifier_few_shot_and_reject(tmp_path):
    words = {"WATER": [300, 600], "HELP": [900, 450], "PAIN": [200, 1200]}
    clf = PrototypeClassifier()
    for lab, fr in words.items():
        for s in range(3):
            clf.add(lab, mfcc(tone(fr, seed=s), SR))
    clf.calibrate()
    assert clf.threshold > 0
    p = clf.predict(mfcc(tone([300, 600], seed=9), SR), margin=0.0)
    assert p.best == "WATER"
    noise = np.random.default_rng(5).standard_normal(SR).astype(np.float32) * 0.3
    assert not clf.predict(mfcc(noise, SR), margin=0.0).accepted
    clf.save(tmp_path / "prof")
    clf2 = PrototypeClassifier.load(tmp_path / "prof")
    assert clf2.counts() == clf.counts() and clf2.threshold == clf.threshold


