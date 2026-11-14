from roles.speech.evaluation.record_demo import summarize


def test_demo_counts_wrong_intents_and_unknown_accepts_against_precision():
    rows = [
        {'expected': 'WATER', 'intent': 'WATER', 'accepted': True},
        {'expected': 'PAIN', 'intent': 'WATER', 'accepted': True},
        {'expected': 'WATER', 'intent': None, 'accepted': False},
        {'expected': 'UNKNOWN', 'intent': 'PAIN', 'accepted': True},
        {'expected': 'UNKNOWN', 'intent': None, 'accepted': False},
    ]
    result = summarize(rows)
    assert result['accepted_precision'] == 1 / 3
    assert result['known_recall'] == 1 / 3
    assert result['wrong_intent_accepts'] == 1
    assert result['unknown_false_accepts'] == 1
    assert result['known_rejections'] == 1


def test_rejecting_everything_has_no_precision_estimate():
    result = summarize([{'expected': 'WATER', 'intent': None, 'accepted': False}])
    assert result['accepted_precision'] is None
    assert result['known_recall'] == 0


def test_full_demo_has_independent_control_and_similar_word_trials():
    from roles.speech.evaluation.record_demo import DEFAULT_INTENTS, test_plan
    plan = test_plan(DEFAULT_INTENTS, 3, 5)
    assert len(DEFAULT_INTENTS) == 7
    assert len(plan) == 40
    assert sum(p['category'] == 'known' for p in plan) == 21
    assert sum(p['category'] == 'unrelated' for p in plan) == 5
    similar = [p for p in plan if p['category'] == 'similar_word']
    assert len(similar) == 14
    assert all(p['expected'] == 'UNKNOWN' for p in similar)
    assert {p['near_intent'] for p in similar} == set(DEFAULT_INTENTS)


def test_take_controls(monkeypatch):
    import pytest
    from roles.speech.evaluation.record_demo import keep_take
    answers = iter(['bad', 'r', '', 'q'])
    monkeypatch.setattr('builtins.input', lambda _: next(answers))
    assert keep_take() is False
    assert keep_take() is True
    with pytest.raises(EOFError):
        keep_take()


def test_enter_stops_capture(monkeypatch):
    import threading
    import numpy as np
    from roles.speech.evaluation.record_demo import record_until_enter
    delivered = threading.Event()
    class Capture:
        dropped_blocks = 0
        def read_chunk(self, timeout_s):
            if not delivered.is_set():
                delivered.set()
                return np.ones(480, dtype=np.float32)
            threading.Event().wait(.01)
            return None
    monkeypatch.setattr('builtins.input', lambda _: delivered.wait(1))
    audio = record_until_enter(Capture())
    assert audio.shape == (480,)
