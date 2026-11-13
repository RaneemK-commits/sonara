import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

"""Verify held-out WAV evaluation and explicit leakage rejection."""
import shutil

import pytest

from scripts.evaluate import evaluate, load_dataset
from roles.speech.evaluation.synthetic_dataset import generate
from sonara.config import load_config
from sonara.recognizer import Recognizer


def test_separate_wav_evaluation_and_leakage(tmp_path):
    generate(tmp_path/'dataset')
    cfg = load_config()
    cfg.raw['recognition']['profile_dir'] = str(tmp_path/'profiles')
    rec = Recognizer(cfg)
    enrollment,test,unknown,manifest = load_dataset(tmp_path/'dataset',rec)
    report = evaluate(enrollment,test,rec,5,.2,unknown)
    assert report['known_test_count'] == 15
    assert report['unknown_test_count'] == 3
    assert 'UNKNOWN' in report['confusion_matrix']
    assert report['latency_ms']['mean'] > 0
    assert len(manifest) == 43
    shutil.copy(tmp_path/'dataset/enrollment/WATER/00.wav',tmp_path/'dataset/test/WATER/leak.wav')
    with pytest.raises(ValueError,match='data leakage'):
        load_dataset(tmp_path/'dataset',rec)
