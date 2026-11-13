"""Synthetic signals validate software behavior, not human recognition accuracy."""
from __future__ import annotations


import numpy as np
import pytest

from sonara.audio.capture import AudioCapture
from sonara.audio.vad import trim_silence
from sonara.audio.wavio import read_wav, resample_linear, write_wav
from sonara.config import load_config
from sonara.models.enrollment import EnrollmentService
from sonara.models.classifier import PrototypeClassifier
from sonara.models.dtw import dtw_distance
from sonara.models.features import FeatureConfig, _dct_matrix, mel_filterbank, mfcc
from sonara.recognizer import Recognizer, profile_path


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


def reference(a, b, band):
    n, m = len(a), len(b)
    width = max(n, m) if band is None else max(abs(n-m), int(np.ceil(band*max(n,m))))
    costs = np.full((n+1, m+1), np.inf)
    lengths = np.zeros((n+1, m+1), int)
    costs[0, 0] = 0
    for i in range(1, n+1):
        for j in range(max(1,i-width), min(m,i+width)+1):
            predecessors = [(i-1,j-1), (i-1,j), (i,j-1)]
            x, y = min(predecessors, key=lambda p: costs[p])
            costs[i,j] = costs[x,y] + np.sqrt(np.mean((a[i-1]-b[j-1])**2))
            lengths[i,j] = lengths[x,y]+1
    return costs[n,m]/lengths[n,m]


@pytest.mark.parametrize('band', [None, 0, .1, .3, 1])
@pytest.mark.parametrize('lengths', [(1,1), (6,6), (5,9), (17,11)])
def test_dtw_reference(band, lengths):
    rng = np.random.default_rng(4)
    a, b = (rng.normal(size=(n, 4)) for n in lengths)
    assert dtw_distance(a,b,band=band) == pytest.approx(reference(a,b,band), abs=1e-10)


def test_band_and_invalid_dtw():
    a = np.arange(12, dtype=float)[:,None]
    b = np.roll(a, 2, axis=0)
    # Compare raw-cost ordering at equal diagonal path lengths only through the reference.
    assert dtw_distance(a,b,band=0) == pytest.approx(np.abs(a-b).mean())
    assert dtw_distance(a,a) == pytest.approx(0, abs=1e-10)
    for bad in (np.empty((0,1)), np.full((4,1),np.nan), np.zeros((601,1)), np.zeros((4,2))):
        assert np.isinf(dtw_distance(a,bad))
    with pytest.raises(ValueError):
        dtw_distance(a,b,band=-1)


@pytest.mark.parametrize('samples', [1, 10, 399, 400, 401, 4800, 80000])
def test_mfcc_short_silence_constant(samples):
    for signal in (np.zeros(samples), np.ones(samples)*1e-6):
        f = mfcc(signal)
        assert f.dtype == np.float32 and f.shape[1] == 39
        assert np.isfinite(f).all()
    f = mfcc(np.ones(samples))
    assert np.isfinite(f).all()


def test_mfcc_configuration_and_math():
    dct = _dct_matrix(40, 13)
    assert dct @ dct.T == pytest.approx(np.eye(13), abs=1e-6)
    fb = mel_filterbank(16000,512,40)
    assert np.all(fb >= 0) and np.all(fb.sum(1) > 0)
    f = mfcc(audio())
    assert f.mean(0) == pytest.approx(np.zeros(39), abs=1e-5)
    assert not np.allclose(f, mfcc(audio(), config=FeatureConfig(normalization='none')))
    for signal in (np.array([]), np.array([np.nan]), np.zeros((4,2))):
        with pytest.raises(ValueError):
            mfcc(signal)
    with pytest.raises(ValueError):
        FeatureConfig(n_fft=128)


def test_audio_validation(cfg):
    rec = Recognizer(cfg)
    for signal in (np.zeros(8000), np.ones(8000)*.1, np.ones(8000), np.array([]),
                   np.full(8000,np.nan), np.zeros((8000,1)), np.ones(100), np.zeros(80001)):
        assert not rec.recognize(signal).accepted
        assert rec.embed(signal) is None
    quiet = audio()*.001
    assert rec.embed(quiet) is not None
    assert len(trim_silence(quiet, 16000)) > .5*16000
    # Long internal pauses remain between first and last voiced frames.
    signal = np.r_[np.zeros(2000), audio(duration=.3), np.zeros(16000), audio(duration=.3),np.zeros(2000)]
    assert len(trim_silence(signal,16000)) > 1.5*16000


def test_rejection_and_calibration():
    rng = np.random.default_rng(1)
    seq = rng.normal(size=(20,39)).astype(np.float32)
    clf = PrototypeClassifier()
    assert not clf.predict(seq).accepted
    clf.add('WATER', seq)
    assert not clf.predict(seq, threshold=0).accepted
    assert not clf.predict(seq, threshold=float('inf')).accepted
    assert clf.predict(seq).accepted
    clf.calibrate()
    assert clf.calibration['requires_more_recordings']
    clf.add('HELP', seq)
    assert not clf.predict(seq).accepted  # equal costs: ambiguous
    clf.calibrate()
    assert not clf.predict(seq).accepted
    assert clf.calibration['requires_more_recordings']


def test_unknown_calibration_limits_threshold():
    rng = np.random.default_rng(3)
    base = rng.normal(size=(10,39)).astype(np.float32)
    clf = PrototypeClassifier()
    for _ in range(3):
        clf.add('WATER', base + rng.normal(scale=.05,size=base.shape))
        clf.add('HELP', base + 2 + rng.normal(scale=.05,size=base.shape))
    clf.calibrate(unknown=[base])
    assert clf.per_intent_thresholds['WATER'] < .1
    assert 'negative_p10' in clf.calibration['intents']['WATER']


def test_profile_persistence_reload_and_isolation(cfg):
    rec = Recognizer(cfg)
    assert not rec.ready
    seq = mfcc(audio())
    for name, label in [('alice','WATER'), ('bob','HELP')]:
        clf = rec.new_classifier()
        clf.profile_id = name
        clf.add(label,seq)
        clf.calibrate()
        clf.save(profile_path(cfg,name))
    rec.reload('alice')
    assert rec.ready and rec.clf.classes == ['WATER']
    assert Recognizer(cfg).profile_id == 'alice'
    changed = PrototypeClassifier.load(profile_path(cfg,'alice'))
    changed.add('PAIN',mfcc(audio(frequencies=(1000,200))))
    changed.save(profile_path(cfg,'alice'))
    assert rec.ready and rec.clf.classes == ['PAIN','WATER']
    rec.reload('bob')
    assert rec.clf.classes == ['HELP']
    assert not list(profile_path(cfg,'bob').glob('*.wav'))
    with pytest.raises(ValueError):
        rec.reload('missing')
    with pytest.raises(ValueError):
        profile_path(cfg,'../outside')
    (profile_path(cfg,'bob')/'templates.npz').write_bytes(b'bad')
    assert not rec.ready  # corruption fails closed even when metadata timestamp is unchanged


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










def test_wav_validation_and_tts_long_wav(tmp_path):
    path = tmp_path/'test.wav'
    write_wav(path,audio(),16000)
    clip,sr = read_wav(path)
    assert sr == 16000 and clip.dtype == np.float32
    assert len(resample_linear(clip,16000,8000)) == len(clip)//2
    path.write_bytes(b'corrupt')
    with pytest.raises(ValueError): read_wav(path)
    write_wav(path,np.zeros(16000*6),16000)
    assert len(read_wav(path, max_seconds=None)[0]) == 16000*6
    with pytest.raises(ValueError): read_wav(path)
    write_wav(path,audio(),16000)
    path.write_bytes(path.read_bytes()[:-4])
    with pytest.raises(ValueError): read_wav(path)




def test_capture_boundaries_without_hardware():
    import queue
    from sonara.audio.vad import StreamingVAD
    cap = AudioCapture.__new__(AudioCapture)
    import threading
    from collections import deque
    cap._recording = threading.Event()
    cap._ambient_lock = threading.Lock()
    cap._ambient_energies = deque(maxlen=333)
    cap.sr, cap.block, cap.max_blocks = 16000, 480, 166
    cap.vad = StreamingVAD(16000,30)
    cap._q = queue.Queue(maxsize=334)
    cap.flush = lambda: None
    for _ in range(167): cap._q.put(np.ones(480,dtype=np.float32)*.1)
    assert cap.record_manual(5).shape == (80000,)
    for _ in range(166): cap._q.put(np.ones(480,dtype=np.float32)*.1)
    captured = cap.record_utterance(1.)
    assert captured.dtype == np.float32 and 0 < len(captured) <= 80000
    with pytest.raises(ValueError): cap.record_manual(5.1)


def test_alsa_command_and_unavailable_device(monkeypatch):
    from sonara.audio.alsa import ALSAInputStream
    monkeypatch.setattr('sonara.audio.alsa.shutil.which',lambda _: None)
    with pytest.raises(RuntimeError,match='alsa-utils'):
        ALSAInputStream(16000,480,'plughw:1,0',lambda *args: None)
    monkeypatch.setattr('sonara.audio.alsa.shutil.which',lambda _: '/usr/bin/arecord')
    stream = ALSAInputStream(16000,480,'plughw:CARD=Set,DEV=0',lambda *args: None)
    assert stream.command == ['/usr/bin/arecord','-q','-D','plughw:CARD=Set,DEV=0',
                              '-t','raw','-f','S16_LE','-c','1','-r','16000']
    stream.close()  # safe even if startup never succeeded


def test_tts_alsa_fallback_without_portaudio(tmp_path, monkeypatch):
    import builtins
    from sonara.tts import Speaker as OutputSpeaker
    original_import = builtins.__import__
    def without_portaudio(name, *args, **kwargs):
        if name == 'sounddevice':
            raise OSError('PortAudio library not found')
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins,'__import__',without_portaudio)
    monkeypatch.setattr('sonara.tts.shutil.which',lambda _: '/usr/bin/aplay')
    played = []
    monkeypatch.setattr('sonara.tts.subprocess.run',lambda argv, **kwargs: played.append(argv))
    speaker = OutputSpeaker.__new__(OutputSpeaker)
    speaker.texts, speaker.enabled, speaker.live, speaker.dir = {'WATER':'Water'}, True, False, tmp_path
    write_wav(tmp_path/'WATER.wav',audio(),16000)
    speaker._play('WATER')
    assert played == [['aplay','-q',str(tmp_path/'WATER.wav')]]


def test_enrollment_service_with_documented_device_hooks(cfg):
    from types import SimpleNamespace
    rec = Recognizer(cfg)
    ctl = SimpleNamespace(recognizer=rec, state="IDLE", capture=Capture(), speaker=Speaker(),
                          enrollment_active=False, _publish=lambda: None)
    service = EnrollmentService(cfg, ctl)
    assert service.start("alice")["enrolling"]
    service.select("WATER")
    for i in range(5):
        assert service.capture(seconds=.6)["pending"]
        assert service.save_sample()["counts"]["WATER"] == i+1
    assert service.capture(seconds=.6, test=True)["prediction"]["intent"] == "WATER"
    assert service.finish()["active_profile"] == "alice"
    assert not ctl.enrollment_active
    assert not list(profile_path(cfg, "alice").rglob("*.wav"))
    service.start("alice")
    assert service.remove("WATER", 4)["counts"]["WATER"] == 4
    service.cancel()
    service.delete("alice")
    assert not rec.ready
    ctl.capture = None
    service.start("bob")
    service.select("HELP")
    with pytest.raises(RuntimeError, match="no device microphone"):
        service.capture()
    service.cancel()
