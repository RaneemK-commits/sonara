import numpy as np
import pytest
from sonara.models.personal import CONTEXTS, PersonalWordCandidate


def tone(frequency):
    t = np.arange(8000)/16000
    return (.1*np.sin(2*np.pi*frequency*t)*np.sin(np.pi*np.arange(8000)/8000)).astype(np.float32)


def candidate():
    model = PersonalWordCandidate()
    for index,label in enumerate(sum(CONTEXTS.values(),())):
        for take in range(2):
            model.add(label,f'{label}:{take}',tone(200+index*180+take*3))
    return model


def test_saved_candidate_preserves_scores_and_separate_contexts(tmp_path):
    model = candidate()
    path = tmp_path/'candidate'
    model.save(path)
    loaded = PersonalWordCandidate.load(path)
    for context,labels in CONTEXTS.items():
        before = model.predict(tone(202),context)
        after = loaded.predict(tone(202),context)
        assert set(after.scores) == set(labels)
        assert after.scores == pytest.approx(before.scores)
        assert before.intent == after.intent
    assert not loaded.predict(np.zeros(8000,np.float32)).accepted


def test_corrupt_candidate_fails_closed(tmp_path):
    path = tmp_path/'candidate'
    candidate().save(path)
    with (path/'references.npz').open('ab') as stream:
        stream.write(b'corrupted')
    with pytest.raises(ValueError,match='checksum'):
        PersonalWordCandidate.load(path)


def test_incomplete_context_rejects_and_families_cannot_cross_labels():
    model = PersonalWordCandidate()
    model.add('WATER','one',tone(200))
    assert not model.predict(tone(200)).accepted
    with pytest.raises(ValueError,match='conflicting'):
        model.add('PAIN','one',tone(400))


def test_live_recognizer_routes_requests_and_fails_closed(tmp_path,monkeypatch):
    from sonara.config import load_config
    from sonara.recognizer import Recognizer
    path=tmp_path/'candidate'
    candidate().save(path)
    monkeypatch.setenv('SONARA_PERSONAL_CANDIDATE',str(path))
    cfg=load_config()
    cfg.root=tmp_path
    rec=Recognizer(cfg)
    assert rec.ready
    assert rec.profile_id=='personal_requests_demo'
    result=rec.recognize(tone(202),manual=True)
    assert set(result.scores)==set(CONTEXTS['requests'])
    assert 'YES' not in result.scores and 'NO' not in result.scores
    with pytest.raises(ValueError,match='override'):
        rec.reload('patient_001')
    (path/'references.npz').unlink()
    assert not rec.ready
    assert not rec.recognize(tone(202)).accepted
    assert 'unavailable' in rec.profile_error


def test_explicit_request_limits_are_validated_and_reported(tmp_path,monkeypatch):
    from sonara.config import load_config
    from sonara.recognizer import Recognizer
    path=tmp_path/'candidate'; candidate().save(path)
    monkeypatch.setenv('SONARA_PERSONAL_CANDIDATE',str(path))
    monkeypatch.setenv('SONARA_PERSONAL_REQUEST_THRESHOLD','.85')
    monkeypatch.setenv('SONARA_PERSONAL_REQUEST_MARGIN','.10')
    cfg=load_config();cfg.root=tmp_path
    rec=Recognizer(cfg)
    assert rec.recognize(tone(202)).threshold==.85
    assert rec.clf.calibration['required_margin']==.10
    monkeypatch.setenv('SONARA_PERSONAL_REQUEST_MARGIN','nan')
    with pytest.raises(ValueError,match='rejection limits'):
        Recognizer(cfg)


def test_relaxed_limits_accept_only_when_both_distance_and_margin_pass(monkeypatch):
    model=candidate()
    monkeypatch.setattr('sonara.models.personal.dtw_distances',
                        lambda *args,**kwargs: [.84,.84,.95,.95,1.2,1.2,1.3,1.3,1.4,1.4])
    audio=tone(202)
    assert not model.predict(audio).accepted
    assert not model.predict(audio,threshold=.85).accepted
    assert not model.predict(audio,required_margin=.10).accepted
    assert model.predict(audio,threshold=.85,required_margin=.10).intent=='WATER'


def test_diagnostic_audio_is_explicit_opt_in(tmp_path,monkeypatch):
    from sonara.config import load_config
    from sonara.recognizer import Recognizer
    path=tmp_path/'candidate'; candidate().save(path)
    monkeypatch.setenv('SONARA_PERSONAL_CANDIDATE',str(path))
    cfg=load_config();cfg.root=tmp_path
    rec=Recognizer(cfg)
    directory=tmp_path/'diagnostics'
    monkeypatch.delenv('SONARA_SPEECH_DIAGNOSTICS',raising=False)
    rec.recognize(tone(202))
    assert not directory.exists()
    monkeypatch.setenv('SONARA_SPEECH_DIAGNOSTICS',str(directory))
    rec.recognize(tone(202))
    assert len(list(directory.glob('*.wav')))==1
    assert len(list(directory.glob('*.json')))==1


def test_focused_boundaries_remove_spikes_preserve_internal_pause():
    from sonara.models.personal import focused_word
    audio=np.zeros(48000,np.float32)
    audio[1600:1920]=.1  # isolated 20 ms click
    audio[24000:28000]=.1
    audio[30000:34000]=.08  # internal pause remains inside word
    crop=focused_word(audio)
    assert 10000<len(crop)<16000
    assert np.max(crop)>.05 and np.min(crop)<0


def test_boundary_retry_requires_agreement(monkeypatch):
    from sonara.models.classifier import Prediction
    model=candidate()
    audio=np.concatenate([np.zeros(16000,np.float32),tone(202),np.zeros(16000,np.float32)])
    for retry_label in ('WATER','HELP'):
        results=iter([Prediction(None,'WATER',.7,.01,.85,{}),
                      Prediction(retry_label,retry_label,.6,.08,.85,{})])
        monkeypatch.setattr(model,'_match',lambda *args:next(results))
        result=model.predict(audio,threshold=.85,required_margin=.05)
        assert result.accepted == (retry_label=='WATER')


def test_closest_label_demo_keeps_distance_and_invalid_audio_rejection(monkeypatch):
    model=candidate()
    distances=[.64,.64,.65,.65,.7,.7,.75,.75,.8,.8]
    monkeypatch.setattr('sonara.models.personal.dtw_distances',lambda *a,**k:distances)
    audio=tone(202)
    assert not model.predict(audio,threshold=.85,required_margin=.05).accepted
    result=model.predict(audio,threshold=.85,required_margin=0)
    assert result.intent=='WATER'
    assert result.reason=='closest-label demo; confirmation required'
    assert not model.predict(audio,threshold=.6,required_margin=0).accepted
    assert not model.predict(np.zeros(8000,np.float32),required_margin=0).accepted



def test_closest_label_demo_uses_one_pass_even_when_distance_rejects(monkeypatch):
    from sonara.models.classifier import Prediction
    model=candidate()
    calls=[]
    def match(*args):
        calls.append(1)
        return Prediction(None,'WATER',1.,.01,.85,{})
    monkeypatch.setattr(model,'_match',match)
    audio=np.concatenate([np.zeros(16000,np.float32),tone(202),np.zeros(16000,np.float32)])
    assert not model.predict(audio,threshold=.85,required_margin=0).accepted
    assert len(calls)==1
