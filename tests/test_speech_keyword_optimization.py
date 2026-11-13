"""Exact batching checks and explicit synthetic-family enrollment behavior."""
import numpy as np
import pytest

from sonara.models.subsequence import subsequence_candidates,subsequence_candidates_many


@pytest.mark.parametrize('penalty',[0.,.05,.2])
@pytest.mark.parametrize('batch_size',[1,3,16])
def test_batched_subsequence_matches_scalar(penalty,batch_size):
    rng=np.random.default_rng(72)
    templates=[rng.normal(size=(n,6)) for n in (1,5,13,8,25)]
    stream=rng.normal(size=(40,6))
    many=subsequence_candidates_many(templates,stream,step_penalty=penalty,batch_size=batch_size)
    for template,actual in zip(templates,many):
        expected=subsequence_candidates(template,stream,step_penalty=penalty)
        assert [(m.start,m.end,m.path_length) for m in actual]==[(m.start,m.end,m.path_length) for m in expected]
        assert [m.distance for m in actual]==pytest.approx([m.distance for m in expected],abs=1e-10)


def test_batched_subsequence_ties_repeats_and_invalid_inputs():
    template=np.zeros((10,4));stream=np.zeros((40,4))
    expected=subsequence_candidates(template,stream)
    assert subsequence_candidates_many([template,template],stream)==[expected,expected]
    assert subsequence_candidates_many([np.zeros((0,4)),np.ones((5,3))],stream)==[[],[]]
    with pytest.raises(ValueError):subsequence_candidates_many([template],stream,batch_size=17)


def recordings(count=2):
    result={}
    for label,frequencies in {'WATER':(300,600),'PAIN':(900,1300)}.items():
        clips=[]
        for i in range(count):
            rng=np.random.default_rng(i);t=np.arange(8000)/16000
            frequency=np.where(t<.25,frequencies[0],frequencies[1])
            clips.append((.15*np.sin(2*np.pi*frequency*t)+.001*rng.standard_normal(len(t))).astype(np.float32))
        result[label]=clips
    return result


def test_five_real_minimum_and_explicit_few_shot_augmentation_families(tmp_path):
    from sonara.models.keywords import KeywordSpotter
    with pytest.raises(ValueError,match='five independent'):KeywordSpotter.enroll(recordings())
    model=KeywordSpotter.enroll(recordings(),allow_few_shot=True,synthetic_per_intent=3,seed=44)
    assert model.references.counts()=={'WATER':5,'PAIN':5}
    assert len(set(model.parent_ids))==4
    assert model.classifier.calibration['requires_more_recordings']
    for d in model.classifier.calibration['intents'].values():
        assert d['independent_recordings']==2 and d['synthetic_variants']==3
        assert d['positive_loo']==2  # Never five: siblings must not inflate calibration.
    model.save(tmp_path/'profile');loaded=KeywordSpotter.load(tmp_path/'profile')
    assert loaded.parent_ids==model.parent_ids
    assert loaded.enrollment_info==model.enrollment_info
    assert loaded.alignment_stride==3
    assert loaded.classifier.calibration==model.classifier.calibration
    assert KeywordSpotter.enroll(recordings(5)).references.counts()=={'WATER':5,'PAIN':5}


def test_source_family_exclusion_removes_parent_and_all_siblings():
    from sonara.models.keyword_training import FamilyClassifier
    clf=FamilyClassifier(['a','b','a','c','d'])
    for label,value in [('WATER',0),('WATER',1),('WATER',.01),('PAIN',3),('PAIN',3.1)]:
        clf.add(label,np.full((12,39),value,np.float32))
    scores=clf.scores(clf.seqs[0],exclude=0)
    assert scores['WATER']==pytest.approx(1.)  # .01 sibling must be excluded.
    assert clf.scores(clf.seqs[0])['WATER']==pytest.approx(.5)  # Distinct-family votes.


def test_synthetic_variants_reproducible_bounded_and_do_not_replace_source():
    from sonara.models.keyword_training import augment_audio
    clip=recordings()['WATER'][0];copy=clip.copy()
    for kind in ('gain','speed','noise'):
        variant=augment_audio(clip,kind,2)
        assert variant.dtype==np.float32 and 4800<=len(variant)<=80000
        assert np.max(np.abs(variant))<=.951
        np.testing.assert_array_equal(variant,augment_audio(clip,kind,2))
    np.testing.assert_array_equal(clip,copy)


def test_legacy_keyword_profile_loads_with_legacy_matching_settings(tmp_path):
    import json
    from sonara.models.keywords import KeywordSpotter
    model=KeywordSpotter.enroll(recordings(),allow_few_shot=True,alignment_stride=1,feature_weights=(1,1,1))
    model.save(tmp_path/'profile')
    path=tmp_path/'profile/keyword.json';meta=json.loads(path.read_text());meta['version']=1
    for key in ('alignment_stride','feature_weights','parent_ids','calibration'):meta.pop(key)
    path.write_text(json.dumps(meta))
    loaded=KeywordSpotter.load(tmp_path/'profile')
    assert loaded.alignment_stride==1 and loaded.feature_weights==(1.,1.,1.)


def test_keyword_cli_import_saves_five_real_takes_without_changing_active_profile(tmp_path):
    import argparse
    from scripts.enroll import enroll_keywords
    from sonara.audio.wavio import write_wav
    from sonara.models.keywords import KeywordSpotter
    from sonara.config import load_config
    cfg=load_config();cfg.root=tmp_path
    for label,clips in recordings(5).items():
        for i,clip in enumerate(clips):write_wav(tmp_path/'wavs'/label/f'{i}.wav',clip,16000)
    (tmp_path/'wavs/WATER/00_bad.WAV').write_bytes(b'corrupt WAV')
    args=argparse.Namespace(replace=False,delete_intent=None,takes=5,from_dir=tmp_path/'wavs',
        allow_few_shot=False,profile='demo',keyword_dir='keyword_profiles',keyword_overwrite=False,
        intents=['WATER','PAIN'],synthetic_variants=2,preserve_word_boundaries=False,keep_audio=False,
        automatic=False,seconds=3.,keyword_scan_s=1.25)
    directory=enroll_keywords(args,cfg);model=KeywordSpotter.load(directory)
    assert model.references.counts()=={'WATER':7,'PAIN':7}
    assert model.stride_samples==20000
    assert all(d['independent_recordings']==5 for d in model.classifier.calibration['intents'].values())
    assert not (directory/'recordings').exists() and not (tmp_path/'data/profiles/active.txt').exists()
    with pytest.raises(ValueError,match='exists'):enroll_keywords(args,cfg)


def test_invalid_optional_augmentation_never_discards_valid_real_takes(monkeypatch):
    from sonara.models import keywords
    def invalid(*args,**kwargs):raise ValueError('optional variant invalid')
    monkeypatch.setattr(keywords,'augment_audio',invalid)
    model=keywords.KeywordSpotter.enroll(recordings(5),synthetic_per_intent=2)
    assert model.references.counts()=={'WATER':5,'PAIN':5}
    assert all(d['synthetic_variants']==0 for d in model.classifier.calibration['intents'].values())


def test_crop_score_cache_reuses_identical_audio_and_invalidates_threshold_changes(monkeypatch):
    from sonara.models.keywords import KeywordSpotter
    model=KeywordSpotter.enroll(recordings(5))
    clips=recordings(5)
    phrase=np.concatenate([clips['PAIN'][0],clips['WATER'][1],clips['PAIN'][2]])
    original=model.classifier.predict;calls=[]
    def count(*args,**kwargs):calls.append(1);return original(*args,**kwargs)
    monkeypatch.setattr(model.classifier,'predict',count)
    first=model.scan(phrase);n=len(calls)
    assert n>0 and model._score_cache
    second=model.scan(phrase)
    assert len(calls)==n
    assert [(e.prediction.intent,e.start_s,e.end_s) for e in first]==[(e.prediction.intent,e.start_s,e.end_s) for e in second]
    model.classifier.threshold=0
    assert not any(e.prediction.accepted for e in model.scan(phrase))
    assert len(calls)>n
    model.reset();assert not model._score_cache


@pytest.mark.parametrize('stride_s',[.25,.33,.75,1.25])
def test_scan_cadence_is_independent_of_audio_chunk_size(monkeypatch,stride_s):
    from sonara.models.keywords import KeywordSpotter
    model=KeywordSpotter.enroll(recordings(5),stride_s=stride_s)
    audio=np.random.default_rng(42).normal(0,.01,128000).astype(np.float32)
    schedules=[]
    for chunk_samples in (480,800,16000):
        model.reset();calls=[]
        def scan(samples,*,offset_s):
            import hashlib
            calls.append((round(offset_s+len(samples)/16000,6),len(samples),hashlib.sha256(samples.tobytes()).hexdigest()))
            return []
        monkeypatch.setattr(model,'scan',scan)
        for i in range(0,len(audio),chunk_samples):model.feed(audio[i:i+chunk_samples])
        assert model._samples_seen==len(audio) and len(model._buffer)<=80000
        schedules.append(calls)
    assert schedules[0]==schedules[1]==schedules[2]
    first=max(.3,stride_s)
    assert schedules[0][0][0]==pytest.approx(first)


def test_invalid_chunk_is_rejected_before_any_partial_scans(monkeypatch):
    from sonara.models.keywords import KeywordSpotter
    model=KeywordSpotter.enroll(recordings(5),stride_s=.25)
    calls=[]
    monkeypatch.setattr(model,'scan',lambda *args,**kwargs:calls.append(1) or [])
    audio=np.ones(16000,np.float32)*.01;audio[-1]=np.nan
    with pytest.raises(ValueError):model.feed(audio)
    assert not calls and model._samples_seen==0 and not len(model._buffer)


def test_real_matcher_events_do_not_depend_on_chunk_delivery_size():
    from sonara.models.keywords import KeywordSpotter
    clips=recordings(5)
    model=KeywordSpotter.enroll(clips)
    t=np.arange(8000)/16000
    frequencies=np.where(t<.25,1700,1900)
    filler=(.15*np.sin(2*np.pi*frequencies*t)).astype(np.float32)
    # One target among out-of-vocabulary sounds; dense known-keyword streams
    # exceed the documented two-proposal-per-window budget.
    phrase=np.concatenate([filler,clips['WATER'][1],filler,np.zeros(16000,np.float32)])
    signatures=[]
    for chunk_samples in (480,16000):
        model.reset();events=[]
        for i in range(0,len(phrase),chunk_samples):events.extend(model.feed(phrase[i:i+chunk_samples]))
        signatures.append([(e.prediction.intent,e.prediction.best,e.start_s,e.end_s,e.observed_until_s)
                           for e in events])
    assert signatures[0]==signatures[1]
    assert any(intent=='WATER' for intent,_,_,_,_ in signatures[0])


@pytest.mark.parametrize('bad',[['not audio'],object(),[np.zeros(2),np.zeros(3)]])
def test_non_numeric_chunk_resets_prior_stream_state(bad):
    from sonara.models.keywords import KeywordSpotter
    model=KeywordSpotter.enroll(recordings(5))
    model.feed(np.ones(3200,np.float32)*.01)
    assert model._samples_seen==3200
    with pytest.raises(ValueError,match='numeric mono'):model.feed(bad)
    assert model._samples_seen==0 and not len(model._buffer) and not model._score_cache
    assert model.scan(object())==[]
