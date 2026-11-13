"""Keyword software checks; generated features/audio are not human accuracy."""
import numpy as np
import pytest

from sonara.models.subsequence import subsequence_dtw
from sonara.models.dtw import dtw_distance


def reference(a, b, ratio=(.5, 2.), penalty=.05):
    n, m = len(a), len(b)
    d = np.full((n+1, m+1), np.inf)
    d[0] = 0
    lengths = np.zeros((n+1, m+1), int)
    starts = np.zeros((n+1, m+1), int)
    starts[0] = np.arange(m+1)
    for i in range(1, n+1):
        for j in range(1, m+1):
            choices = [(d[i-1,j-1],i-1,j-1), (d[i-1,j]+penalty,i-1,j), (d[i,j-1]+penalty,i,j-1)]
            cost,x,y = min(choices, key=lambda c:c[0])
            d[i,j] = cost + np.sqrt(np.mean((a[i-1]-b[j-1])**2))
            lengths[i,j] = lengths[x,y]+1
            starts[i,j] = starts[x,y]
    candidates = [(d[n,j]/lengths[n,j], starts[n,j], j, lengths[n,j]) for j in range(1,m+1)
                  if max(1,int(np.ceil(n*ratio[0]))) <= j-starts[n,j] <= int(np.floor(n*ratio[1]))]
    return min(candidates,key=lambda c:c[0]) if candidates else None


@pytest.mark.parametrize('shape',[(1,8),(5,20),(12,8),(10,30)])
@pytest.mark.parametrize('penalty',[0.,.05,.2])
def test_subsequence_matches_simple_reference(shape,penalty):
    rng=np.random.default_rng(7)
    a,b=(rng.normal(size=(n,4)) for n in shape)
    actual=subsequence_dtw(a,b,step_penalty=penalty)
    expected=reference(a,b,penalty=penalty)
    if expected is None:
        assert actual is None
    else:
        assert actual.distance==pytest.approx(expected[0],abs=1e-10)
        assert (actual.start,actual.end,actual.path_length)==expected[1:]


def test_locates_keyword_inside_unrelated_continuous_features():
    rng=np.random.default_rng(40)
    keyword=rng.normal(size=(30,39))
    stream=np.vstack([rng.normal(4,1,(40,39)),keyword,rng.normal(-4,1,(50,39))])
    found=subsequence_dtw(keyword,stream)
    assert (found.start,found.end)==(40,70)
    assert found.distance==pytest.approx(0,abs=1e-10)
    assert dtw_distance(keyword,stream)>1


def test_duration_constraint_rejects_collapsed_match_and_invalid_input():
    a=np.zeros((20,3)); b=np.ones((5,3))
    assert subsequence_dtw(a,b) is None
    for bad in [np.empty((0,3)),np.full((10,3),np.nan),np.zeros((601,3)),np.zeros((4,2))]:
        assert subsequence_dtw(a,bad) is None
    with pytest.raises(ValueError):subsequence_dtw(a,a,duration_ratio=(0,2))


def signal(frequencies, seed=0):
    rng=np.random.default_rng(seed)
    t=np.arange(8000)/16000
    f=np.array(frequencies)[np.minimum(np.arange(len(t))*len(frequencies)//len(t),len(frequencies)-1)]
    return (.15*np.sin(2*np.pi*f*t)+.001*rng.standard_normal(len(t))).astype(np.float32)


def spotter():
    from sonara.models.keywords import KeywordSpotter
    return KeywordSpotter.enroll({label:[signal(freq,s) for s in range(3)]
                                 for label,freq in {'WATER':(300,600),'PAIN':(900,1300)}.items()},allow_few_shot=True,stride_s=.5)


def test_shared_scaling_and_localization_inside_generated_phrase(tmp_path):
    from sonara.models.keywords import KeywordSpotter
    model=spotter()
    phrase=np.concatenate([signal((1700,1900)),signal((300,600),19),signal((1600,1800))])
    events=model.scan(phrase)
    assert events
    water=[e for e in events if e.prediction.best=='WATER']
    assert water
    found=min(water,key=lambda e:e.prediction.distance)
    assert abs(found.start_s-.5)<.15 and abs(found.end_s-1.)<.15
    assert found.prediction.accepted
    noise=np.random.default_rng(7).normal(0,.05,24000).astype(np.float32)
    assert not any(e.prediction.accepted for e in model.scan(noise))
    model.save(tmp_path/'voice')
    restored=KeywordSpotter.load(tmp_path/'voice')
    again=restored.scan(phrase)
    assert [(e.start_s,e.end_s,e.prediction.best,e.prediction.accepted) for e in events]==[
        (e.start_s,e.end_s,e.prediction.best,e.prediction.accepted) for e in again]
    assert not (tmp_path/'voice/metadata.json').exists()  # cannot be loaded as an utterance profile


def test_rejects_old_cmvn_profiles_and_bounds_stream_memory():
    from sonara.models.keywords import KeywordSpotter
    from sonara.models.classifier import PrototypeClassifier
    with pytest.raises(ValueError,match='raw-MFCC'):
        KeywordSpotter(PrototypeClassifier())
    model=spotter()
    for _ in range(20):
        model.feed(np.zeros(16000,dtype=np.float32))
    assert len(model._buffer)==80000
    with pytest.raises(ValueError):model.feed(np.array([np.nan],np.float32))
    assert not len(model._buffer)


def test_stream_suppresses_duplicate_accepts_and_reset_clears_state(monkeypatch):
    from sonara.models.keywords import KeywordEvent
    from sonara.models.classifier import Prediction
    model=spotter()
    event=KeywordEvent(.1,.5,1.,Prediction('WATER','WATER',.1,.4,.8,{'WATER':.1,'PAIN':.5}))
    monkeypatch.setattr(model,'scan',lambda audio,offset_s:[event])
    assert model.feed(np.zeros(8000,np.float32))==[event]
    assert model.feed(np.zeros(8000,np.float32))==[]
    model.reset()
    assert model.feed(np.zeros(8000,np.float32))==[event]


def test_localizes_repeated_keywords_in_same_window():
    from sonara.models.subsequence import subsequence_candidates
    rng=np.random.default_rng(122)
    word=rng.normal(size=(15,8))
    phrase=np.vstack([np.full((20,8),5.),word,np.full((20,8),-5.),word,np.full((20,8),5.)])
    matches=subsequence_candidates(word,phrase,max_matches=2)
    assert {(m.start,m.end) for m in matches}=={(20,35),(55,70)}


def test_event_metrics_count_duplicates_wrong_labels_and_missed_events():
    from roles.speech.evaluation.evaluate_keyword_streams import event_metrics
    truth=[{'intent':'WATER','start_s':1.,'end_s':2.},{'intent':'PAIN','start_s':4.,'end_s':5.}]
    good={'intent':'WATER','start_s':1.,'end_s':2.,'observed_until_s':2.5,'accepted':True}
    result=event_metrics(truth,[good,{**good,'observed_until_s':3.},{**good,'intent':'PAIN'}],10.)
    assert result['correct_events']==1 and result['missed_events']==1
    assert result['false_accepted_events']==2 and result['duplicate_accepted_events']==1
    assert result['event_recall']==.5 and result['detection_delay_s']==[.5]


def test_annotated_wav_stream_evaluator_runs_offline_and_does_not_treat_silence_as_success(tmp_path):
    import json
    from sonara.audio.wavio import write_wav
    from roles.speech.evaluation.evaluate_keyword_streams import run
    model=spotter();model.save(tmp_path/'profile')
    write_wav(tmp_path/'negative.wav',np.zeros(16000,np.float32),16000)
    manifest=tmp_path/'streams.json'
    manifest.write_text(json.dumps({'streams':[{'file':'negative.wav','events':[]}]}))
    report=run(tmp_path/'profile',manifest,tmp_path/'report.json')
    assert report['summary']['truth_events']==0
    assert report['summary']['event_recall'] is None
    assert report['summary']['false_accepted_events']==0


def test_word_enrollment_trims_padded_fixed_take_but_can_preserve_manual_boundaries():
    from sonara.models.keywords import KeywordSpotter
    recordings={name:[np.concatenate([np.zeros(16000,np.float32),signal(freq,i),np.zeros(16000,np.float32)])
                      for i in range(2)] for name,freq in {'WATER':(300,600),'PAIN':(900,1300)}.items()}
    automatic=KeywordSpotter.enroll(recordings,allow_few_shot=True)
    manual=KeywordSpotter.enroll(recordings,trim_endpoints=False,allow_few_shot=True)
    assert max(map(len,automatic.references.seqs))<max(map(len,manual.references.seqs))/2


def test_capture_chunk_api_reuses_queue_and_refuses_concurrent_recording():
    import queue,threading
    from sonara.audio.capture import AudioCapture
    capture=AudioCapture.__new__(AudioCapture)
    capture._q=queue.Queue(maxsize=2);capture._recording=threading.Event()
    chunk=np.zeros(480,np.float32);capture._q.put(chunk)
    assert capture.read_chunk(0) is chunk
    assert capture.read_chunk(0) is None
    capture._recording.set()
    for _ in range(3):capture._cb(np.zeros((480,1),np.float32),480,None,None)
    assert capture.dropped_blocks==1
    with pytest.raises(RuntimeError,match='audio lock'):capture.read_chunk(0)
    with pytest.raises(ValueError):capture.read_chunk(2)
