"""Deterministic composition/noise checks, not speech-accuracy measurements."""
import numpy as np
import pytest

from roles.speech.evaluation.noisy_streams import add_noise, compose, select_additional
from roles.speech.evaluation.torgo import SPEAKERS


def test_composition_preserves_target_and_records_exact_timestamps():
    target=np.linspace(-.2,.2,8000,dtype=np.float32)
    parts=[(np.ones(4000,np.float32)*.1,{'file':'before.wav','transcription':'other'}),
           (target,{'file':'target.wav','transcription':'sip','label':'SIP','target':True}),
           (np.ones(4000,np.float32)*.2,{'file':'after.wav','transcription':'word'})]
    audio,events,segments,mask=compose(parts,45)
    again=compose(parts,45)
    assert np.array_equal(audio,again[0]) and events==again[1]
    assert len(events)==1
    start,end=[round(events[0][key]*16000) for key in ('start_s','end_s')]
    np.testing.assert_array_equal(audio[start:end],target)
    assert mask[start:end].all()
    assert all(s['end_s']>s['start_s'] for s in segments)
    assert not mask[-16000:].any()


@pytest.mark.parametrize('condition,snr',[('background_20db',20),('background_10db',10)])
def test_noise_snr_is_measured_reproducible_and_does_not_clip(condition,snr):
    rng=np.random.default_rng(4)
    audio=np.zeros(40000,np.float32);audio[8000:32000]=rng.normal(0,.1,24000)
    mask=np.abs(audio)>0
    noisy,meta=add_noise(audio,mask,condition,8)
    assert meta['measured_speech_snr_db']==pytest.approx(snr,abs=.15)
    assert meta['clipped_fraction']==0
    assert np.max(np.abs(noisy))<=.951
    np.testing.assert_array_equal(noisy,add_noise(audio,mask,condition,8)[0])


def test_gap_noise_does_not_change_target_waveform():
    audio=np.r_[np.zeros(8000),np.ones(8000)*.1,np.zeros(8000)].astype(np.float32)
    mask=audio!=0
    noisy,meta=add_noise(audio,mask,'gap_noise',9)
    np.testing.assert_array_equal(noisy[mask],audio[mask])
    assert np.any(noisy[~mask]!=0)
    assert meta['measured_speech_snr_db'] is None


def test_new_context_selection_excludes_enrollment_takes_channels_and_target_text():
    base={'profiles':[{'speaker':speaker,'references':[],'queries':[]} for speaker in SPEAKERS]}
    rows=[]
    for speaker in ('F03','M02','M03'):
        for i in range(15):
            rows.append({'file':f'{speaker}_1_headMic_{i:04d}.wav','speaker':speaker,'session':'1',
                         'utterance':f'{i:04d}','mic':'headMic','speech_status':'dysarthria','duration':1.,
                         'transcription':'a different word' if i else 'yes please'})
        next(p for p in base['profiles'] if p['speaker']==speaker)['references'].append(rows[-1])
    selected=select_additional(rows,base,count=12)
    for profile in selected['profiles']:
        additions=[e for e in profile['queries'] if e.get('additional_filler')]
        if profile['speaker'] in ('F03','M02','M03'):
            assert len(additions)==12
            assert all(e['transcription']=='a different word' for e in additions)
            assert not {e['file'] for e in additions}&{e['file'] for e in profile['references']}
