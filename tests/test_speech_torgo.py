"""Corpus protocol checks use metadata only, without network or clinical claims."""
import pytest

from roles.speech.evaluation.torgo import SPEAKERS, WORDS, metrics, select, source_info, take_key, validate


def metadata():
    rows = []
    for speaker in SPEAKERS:
        for index, text in enumerate((*WORDS, 'other')):
            for take in range(3):
                for mic in ('headMic', 'arrayMic'):
                    rows.append({'file': f'{speaker}_1_{mic}_{index*3+take:04d}.wav',
                                 'duration': 1., 'speech_status': 'dysarthria', 'transcription': text})
    return rows


def test_protocol_is_deterministic_and_excludes_simultaneous_microphone_leakage():
    rows = metadata()
    manifest = select(rows)
    assert manifest == select(list(reversed(rows)))
    validate(manifest)
    assert len(manifest['profiles']) == len(SPEAKERS)
    for profile in manifest['profiles']:
        assert len(profile['references']) == 10
        assert sum(r['category'] == 'known' for r in profile['queries']) == 5
        assert all(source_info(r['file'])['mic'] == 'headMic' for r in profile['references'] + profile['queries'])
    assert take_key(rows[0]) == take_key(rows[1])


def test_rejects_insufficient_repetitions_instead_of_duplicating_enrollment():
    rows = metadata()
    rows = [r for r in rows if r['file'] != 'F03_1_headMic_0000.wav']
    with pytest.raises(ValueError, match='three independent'):
        select(rows)


@pytest.mark.parametrize('change', ['channel', 'take', 'pcm', 'label', 'speaker'])
def test_manifest_rejects_leakage_and_label_errors(change):
    manifest = select(metadata())
    profile = manifest['profiles'][0]
    reference, query = profile['references'][0], profile['queries'][0]
    if change == 'channel':
        query['file'] = query['file'].replace('headMic', 'arrayMic')
    elif change == 'take':
        query['file'] = reference['file']
    elif change == 'pcm':
        reference['source_pcm_sha256'] = query['source_pcm_sha256'] = 'identical'
    elif change == 'label':
        query['label'] = 'WATER'
    else:
        query['file'] = query['file'].replace('F03', 'M01')
    with pytest.raises(ValueError):
        validate(manifest)


def test_metrics_include_rejections_in_known_denominator_and_separate_impostors():
    base = {'valid_audio': True, 'latency_ms': 1., 'best': 'YES'}
    rows = [{**base, 'category': 'known', 'truth': 'YES', 'intent': 'YES', 'accepted': True},
            {**base, 'category': 'known', 'truth': 'NO', 'intent': None, 'accepted': False},
            {**base, 'category': 'impostor', 'truth': 'UNKNOWN', 'intent': 'YES', 'accepted': True},
            {**base, 'category': 'unknown', 'truth': 'UNKNOWN', 'intent': None, 'accepted': False}]
    result = metrics(rows)
    assert result['correct_intent_rate'] == .5
    assert result['accuracy_among_accepted_known'] == 1.
    assert result['known_rejection_rate'] == .5
    assert result['impostor']['false_acceptance_rate'] == 1.
    assert result['unknown']['false_acceptance_rate'] == 0.
