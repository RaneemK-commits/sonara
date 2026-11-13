import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

"""Corpus adaptation/leakage checks use generated signals; no network or public audio."""
from copy import deepcopy
import hashlib

import numpy as np
import pytest

from roles.speech.evaluation.prepare_real_corpus import bounded_audio, normalize_text
from roles.speech.evaluation.evaluate_real_corpus import checked_path, validate_manifest


def signal(seconds):
    t=np.arange(int(16000*seconds))/16000
    return (.1*np.sin(2*np.pi*300*t)).astype(np.float32)


def test_complete_reference_not_truncated_and_unknown_windows_labeled():
    with pytest.raises(ValueError,match='exceeds five seconds'):
        bounded_audio(signal(6),16000,False)
    clip,meta=bounded_audio(signal(6),16000,True)
    assert len(clip)==80000 and meta['kind']=='five_second_unknown_window'
    clip,meta=bounded_audio(np.r_[np.zeros(16000),signal(2),np.zeros(16000)].astype(np.float32),16000,False)
    assert 2<len(clip)/16000<3 and meta['kind']=='complete_utterance'
    # Internal pauses are retained, even if they make a reference too long.
    with pytest.raises(ValueError,match='exceeds five seconds'):
        bounded_audio(np.r_[signal(2),np.zeros(32000),signal(2)].astype(np.float32),16000,False)
    with pytest.raises(ValueError): bounded_audio(signal(1),8000,True)
    with pytest.raises(ValueError): bounded_audio(np.zeros(16000),16000,True)


def manifest():
    return {'references':[{'label':'PHRASE_01','source':'a.wav','source_pcm_sha256':'a','wav_sha256':'wa','split':'train','kind':'complete_utterance'},
                          {'label':'PHRASE_02','source':'b.wav','source_pcm_sha256':'b','wav_sha256':'wb','split':'train','kind':'complete_utterance'}],
            'queries':[{'source':'c.wav','source_pcm_sha256':'c','wav_sha256':'wc','split':'test','kind':'five_second_unknown_window'}]}


def test_cross_source_leakage_and_reused_query_rejected():
    good=manifest()
    validate_manifest(good)
    for field in ('source','source_pcm_sha256','wav_sha256'):
        bad=deepcopy(good)
        bad['queries'][0][field]=bad['references'][0][field]
        with pytest.raises(ValueError,match='reused'):
            validate_manifest(bad)
    bad=deepcopy(good)
    bad['queries'].append(deepcopy(bad['queries'][0]))
    with pytest.raises(ValueError): validate_manifest(bad)
    bad=deepcopy(good)
    bad['references'][0]['kind']='five_second_unknown_window'
    with pytest.raises(ValueError): validate_manifest(bad)


def test_local_bundle_checksums_and_paths(tmp_path):
    local=tmp_path/'a.wav'
    local.write_bytes(b'fixture')
    assert checked_path(tmp_path,{'file':'a.wav','wav_sha256':hashlib.sha256(b'fixture').hexdigest()})==local
    with pytest.raises(ValueError,match='checksum'):
        checked_path(tmp_path,{'file':'a.wav','wav_sha256':'bad'})
    with pytest.raises(ValueError,match='escapes'):
        checked_path(tmp_path,{'file':'../outside','wav_sha256':'bad'})
    assert normalize_text('  VIRUS  ist klein.\n')=='virus ist klein.'
