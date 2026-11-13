"""Device/UI integration checks: run after applying device.patch in an isolated checkout."""
from __future__ import annotations


import threading


import numpy as np


import pytest


from fastapi.testclient import TestClient


from sonara.audio.capture import AudioCapture


from sonara.audio.vad import trim_silence


from sonara.audio.wavio import read_wav, resample_linear, write_wav


from sonara.config import load_config


from sonara.controller import Controller


from sonara.models.enrollment import EnrollmentService


from sonara.hw.mcu import NullMCU


from sonara.models.classifier import PrototypeClassifier


from sonara.models.dtw import dtw_distance


from sonara.models.features import FeatureConfig, _dct_matrix, mel_filterbank, mfcc


from sonara.recognizer import Recognizer, profile_path


from sonara.server.app import create_app


from sonara.server.hub import Hub


from sonara.store import RequestStore


def audio(seed=0, frequencies=(300, 600), duration=.6):
    rng = np.random.default_rng(seed)
    t = np.arange(int(16000*duration)) / 16000
    f = np.array(frequencies)[np.minimum((np.arange(len(t))*len(frequencies)//len(t)), len(frequencies)-1)]
    signal = .15 * np.sin(2*np.pi*f*t) + .003*rng.standard_normal(len(t))
    return signal.astype(np.float32)


@pytest.fixture
def cfg(tmp_path):
    cfg = load_config()
    cfg.raw['recognition']['profile_dir'] = str(tmp_path/'profiles')
    cfg.raw['recognition'].pop('threshold', None)
    return cfg


class Speaker:
    def __init__(self): self.said = []
    def say(self, text): self.said.append(text)
    say_now = say
    def wait_idle(self): pass


class Capture:
    def __init__(self): self.calls = 0; self.closed = False
    def flush(self): pass
    def close(self): self.closed = True
    def record_manual(self, seconds): self.calls += 1; return audio(seed=self.calls)
    def record_utterance(self, wait_s): return self.record_manual(.6)


def setup(cfg, capture=None):
    store, hub, speaker = RequestStore(':memory:'), Hub(), Speaker()
    ctl = Controller(cfg,store,hub,speaker,NullMCU(),Recognizer(cfg),capture)
    return ctl, store, create_app(cfg,store,hub,ctl)


def test_enrollment_end_to_end_device_capture(cfg):
    cap = Capture()
    ctl,store,app = setup(cfg,cap)
    with TestClient(app) as client:
        assert client.post('/api/enrollment/capture', json={}).status_code == 422
        assert client.post('/api/enrollment/start',json={'profile_id':'alice'}).status_code == 200
        assert client.post('/api/room/input',json={'action':'talk'}).status_code == 409
        assert client.post('/api/enrollment/intent',json={'intent':'WATER'}).status_code == 200
        for i in range(5):
            assert client.post('/api/enrollment/capture',json={'seconds':.6}).json()['pending']
            status = client.post('/api/enrollment/sample').json()
            assert status['counts']['WATER'] == i+1
        test = client.post('/api/enrollment/test',json={'seconds':.6}).json()
        assert test['prediction']['intent'] == 'WATER'
        assert test['prediction']['accepted']
        assert store.history() == []
        status = client.post('/api/enrollment/finish').json()
        assert not status['enrolling'] and status['active_profile'] == 'alice'
        assert not list(profile_path(cfg,'alice').rglob('*.wav'))
        # A recognized request still cannot send itself.
        ctl._handle_audio(audio(seed=10))
        assert ctl.state == 'AWAIT_CONFIRM' and store.history() == []
        ctl._on_confirm()
        assert store.history()[0]['intent'] == 'WATER'
        ctl._on_cancel()
        assert client.post('/api/enrollment/start',json={'profile_id':'alice'}).status_code == 200
        assert client.delete('/api/enrollment/intents/WATER/samples/4').json()['counts']['WATER'] == 4
        assert client.delete('/api/enrollment/intents/WATER').json()['counts'] == {}
        assert client.post('/api/enrollment/cancel').status_code == 200
        assert client.delete('/api/profiles/alice').status_code == 200
        assert not ctl.recognizer.ready
    assert cap.closed


def test_no_mic_and_invalid_profile(cfg):
    ctl,store,app = setup(cfg)
    with TestClient(app) as c:
        c.post('/api/enrollment/start',json={'profile_id':'alice'})
        c.post('/api/enrollment/intent',json={'intent':'HELP'})
        assert c.post('/api/enrollment/capture',json={}).status_code == 503
        assert c.post('/api/profiles/missing/load').status_code == 422
        assert c.post('/api/enrollment/start',json={'profile_id':'../bad'}).status_code == 422
        assert c.post('/api/enrollment/capture',json={'seconds':10}).status_code == 422
        c.post('/api/enrollment/cancel')
        ctl._on_talk()
        assert ctl.state == 'IDLE' and not store.history()


def test_microphone_exclusion_and_bounded_queue(cfg):
    ctl,_,app = setup(cfg,Capture())
    with TestClient(app) as c:
        acquired, release = threading.Event(), threading.Event()
        def hold():
            with ctl.audio_lock:
                acquired.set()
                release.wait(3)
        worker = threading.Thread(target=hold)
        worker.start()
        assert acquired.wait(1)
        try:
            assert c.post('/api/enrollment/start',json={'profile_id':'alice'}).status_code == 409
            ctl._on_talk()
            assert ctl.capture.calls == 0
            # Health remains available while device capture owns the mic lock.
            assert c.get('/api/health').status_code == 200
        finally:
            release.set()
            worker.join()
    for _ in range(100): ctl.submit('talk')
    assert ctl._q.qsize() <= 32


def test_early_and_stale_confirm_cannot_dispatch(cfg):
    ctl,store,_ = setup(cfg)
    ctl.submit('confirm')
    assert ctl._q.empty()
    ctl._accept('WATER',None)
    ctl.submit('confirm')
    _, token = ctl._q.get_nowait()
    ctl._accept('HELP',None)
    ctl._on_confirm(token)
    assert store.history() == []
    ctl.submit('confirm')
    _, token = ctl._q.get_nowait()
    ctl._on_confirm(token)
    assert store.history()[0]['intent'] == 'HELP'


