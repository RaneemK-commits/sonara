"""Exact matching, cross-platform evaluation, and fail-closed recording improvements."""
from __future__ import annotations

import builtins
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sonara.models.dtw import dtw_distance, dtw_distances
from roles.speech.evaluation import memory


@pytest.mark.parametrize('band',[None,0.,.1,.4,1.])
@pytest.mark.parametrize('length',[1,9,51])
def test_batched_dtw_matches_scalar_for_variable_lengths(band,length):
    rng=np.random.default_rng(71)
    query=rng.normal(size=(length,39))
    templates=[rng.normal(size=(n,39)) for n in (1,2,8,9,17,31,51,60)]
    expected=[dtw_distance(query,template,band=band) for template in templates]
    for batch in (1,3,16):
        assert dtw_distances(query,templates,band=band,batch_size=batch)==pytest.approx(expected,abs=1e-11)


def test_batched_dtw_ties_and_invalid_templates():
    query=np.arange(9,dtype=float)[:,None]
    templates=[query,np.repeat(query,2,axis=0),np.zeros((1,1)),np.ones((19,1)),
               np.empty((0,1)),np.ones((4,2)),np.full((3,1),np.nan),np.zeros((601,1))]
    assert dtw_distances(query,templates)==pytest.approx([dtw_distance(query,b) for b in templates],abs=1e-11)
    assert all(np.isinf(d) for d in dtw_distances(np.empty((0,1)),templates))
    assert dtw_distances(query,[])==[]
    with pytest.raises(ValueError): dtw_distances(query,templates,batch_size=17)
    with pytest.raises(ValueError): dtw_distances(query,templates*13)
    with pytest.raises(ValueError): dtw_distances(query,templates,band=-.1)


def test_evaluation_imports_when_resource_is_unavailable(monkeypatch):
    original=builtins.__import__
    def without_resource(name,*args,**kwargs):
        if name=='resource': raise ModuleNotFoundError('resource is not available on Windows')
        return original(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',without_resource)
    assert memory.peak_process_rss_mib() is None
    for name in ('scripts.evaluate','scripts.benchmark','roles.speech.evaluation.evaluate_real_corpus'):
        importlib.reload(importlib.import_module(name))
    monkeypatch.setattr(memory.sys,'platform','win32')
    assert memory.peak_process_rss_mib() is None


def test_linux_memory_units(monkeypatch):
    original=builtins.__import__
    def resource_fixture(name,*args,**kwargs):
        if name=='resource': return SimpleNamespace(RUSAGE_SELF=0,getrusage=lambda _:SimpleNamespace(ru_maxrss=2048))
        return original(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',resource_fixture)
    monkeypatch.setattr(memory.sys,'platform','linux')
    assert memory.peak_process_rss_mib()==2.


def capture_fixture():
    from collections import deque
    import queue,threading
    from sonara.audio.capture import AudioCapture
    from sonara.audio.vad import StreamingVAD
    cap=AudioCapture.__new__(AudioCapture)
    cap._recording=threading.Event()
    cap._ambient_lock=threading.Lock()
    cap._ambient_energies=deque(maxlen=333)
    cap._q=queue.Queue(maxsize=334)
    cap.vad=StreamingVAD(16000,30)
    cap.sr,cap.block=16000,480
    return cap


def test_vad_ambient_noise_and_quiet_speech():
    from sonara.audio.vad import StreamingVAD
    rng=np.random.default_rng(1)
    vad=StreamingVAD(16000,30)
    vad.reset(noise_floor=.003)
    assert all(vad.update(rng.normal(0,.003,480)) is None for _ in range(20))
    assert 'start' in [vad.update(rng.normal(0,.03,480)) for _ in range(3)]
    vad.reset(noise_floor=.000003)
    assert 'start' in [vad.update(rng.normal(0,.0002,480)) for _ in range(3)]
    with pytest.raises(ValueError): vad.reset(noise_floor=float('nan'))


def test_capture_learns_idle_noise_but_not_the_recording(monkeypatch):
    cap=capture_fixture()
    rng=np.random.default_rng(7)
    for _ in range(30): cap._cb(rng.normal(0,.003,(480,1)),480,None,None)
    def segment(wait_s):
        assert .002<cap.vad.noise_floor<.004
        before=tuple(cap._ambient_energies)
        cap._cb(rng.normal(0,.2,(480,1)),480,None,None)
        assert tuple(cap._ambient_energies)==before
        return None
    monkeypatch.setattr(cap,'_record_segment',segment)
    assert cap.record_utterance(.1) is None
    assert not cap._recording.is_set()
    def failed(seconds): raise RuntimeError('capture disconnected')
    monkeypatch.setattr(cap,'_record_manual',failed)
    with pytest.raises(RuntimeError): cap.record_manual(1.)
    assert not cap._recording.is_set()


def profile_fixture(tmp_path):
    from sonara.config import load_config
    from sonara.recognizer import Recognizer,profile_path
    cfg=load_config()
    cfg.raw['recognition']['profile_dir']=str(tmp_path/'profiles')
    cfg.raw['recognition'].pop('threshold',None)
    rec=Recognizer(cfg)
    clf=rec.new_classifier()
    clf.profile_id='alice'
    clf.add('WATER',np.random.default_rng(1).normal(size=(10,39)).astype(np.float32))
    clf.save(profile_path(cfg,'alice'))
    rec.reload('alice')
    return cfg,rec


def test_failed_explicit_profile_switch_keeps_current_patient(tmp_path):
    from sonara.recognizer import profile_path
    cfg,rec=profile_fixture(tmp_path)
    bad=profile_path(cfg,'broken')
    bad.mkdir()
    (bad/'metadata.json').write_text('{}')
    with pytest.raises(ValueError,match='templates.npz'): rec.reload('broken')
    assert rec.profile_id=='alice' and rec.ready and rec.clf.classes==['WATER']
    assert (bad.parent/'active.txt').read_text()=='alice'


@pytest.mark.parametrize("selection", ["../someone_else", "", " " * 257])
def test_corrupt_active_selection_does_not_fall_back_to_other_patient(tmp_path, selection):
    from sonara.recognizer import Recognizer,profile_path
    cfg,rec=profile_fixture(tmp_path)
    (profile_path(cfg).parent/'active.txt').write_text(selection)
    restarted=Recognizer(cfg)
    assert not restarted.ready and 'active profile selection' in restarted.profile_error
    restarted.reload('alice')
    assert restarted.ready and restarted.profile_id=='alice'


def test_corrupt_profile_recovers_when_original_files_restored(tmp_path):
    import os,json
    from sonara.recognizer import profile_path
    cfg,rec=profile_fixture(tmp_path)
    metadata=profile_path(cfg,'alice')/'metadata.json'
    original,stat=metadata.read_bytes(),metadata.stat()
    bad=json.loads(original)
    bad['feature_config']=[]
    metadata.write_text(json.dumps(bad))
    assert not rec.ready
    metadata.write_bytes(original)
    os.utime(metadata,ns=(stat.st_atime_ns,stat.st_mtime_ns))
    assert rec.ready and not rec.profile_error


def test_profile_directory_identity_mismatch_rejects(tmp_path):
    import json
    from sonara.recognizer import profile_path
    cfg,rec=profile_fixture(tmp_path)
    metadata=profile_path(cfg,'alice')/'metadata.json'
    data=json.loads(metadata.read_text());data['profile_id']='bob'
    metadata.write_text(json.dumps(data))
    assert not rec.ready and 'does not match' in rec.profile_error


def test_rejection_logs_matching_diagnostics_without_audio(tmp_path, caplog):
    cfg, rec = profile_fixture(tmp_path)
    import numpy as np
    rec.recognize(np.zeros(16000, dtype=np.float32))
    assert 'accepted=False' in caplog.text
    assert 'distance=' in caplog.text and 'required_margin=' in caplog.text
    assert 'processing_ms=' in caplog.text and 'invalid or silent recording' in caplog.text


def test_calibration_distinguishes_overlap_from_too_few_examples():
    from sonara.models.classifier import PrototypeClassifier
    rng = np.random.default_rng(900)
    clf = PrototypeClassifier()
    base = rng.normal(size=(12, 39)).astype(np.float32)
    for label in ('WATER', 'HELP'):
        for _ in range(3):
            clf.add(label, base + rng.normal(0, .03, base.shape).astype(np.float32))
    clf.calibrate()
    assert clf.calibration['requires_more_recordings']
    assert all(d['status'] in ('overlapping_intents', 'margin_not_separated')
               for d in clf.calibration['intents'].values())
    assert all(d['loo_gap_p10'] < clf.margin for d in clf.calibration['intents'].values())
