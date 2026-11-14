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
