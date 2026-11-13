"""Playback lifecycle checks with simulated backends; no microphone or speaker needed."""
import sys
import threading
from types import SimpleNamespace

import pytest

from sonara.config import Config
from sonara.tts import Speaker


@pytest.fixture
def cfg(tmp_path):
    return Config(raw={}, intents=[], prompts={}, root=tmp_path)


def backend(monkeypatch, cfg, *, wait=lambda: None):
    cfg.path("assets/tts").mkdir(parents=True)
    for key in ("a", "b"):
        cfg.path(f"assets/tts/{key}.wav").touch()
    monkeypatch.setattr("sonara.tts.read_wav", lambda *a, **kw: ([], 16000))
    monkeypatch.setitem(sys.modules, "sounddevice", SimpleNamespace(
        play=lambda *a: None, wait=wait))


def test_replacement_keeps_active_cancels_pending_and_timeout_does_not_cancel(cfg, monkeypatch):
    active, release = threading.Event(), threading.Event()

    def wait():
        active.set()
        assert release.wait(3)

    backend(monkeypatch, cfg, wait=wait)
    events, threads = [], []

    def callback(event):
        events.append(event)
        threads.append(threading.get_ident())

    speaker = Speaker(cfg, on_playback=callback)
    speaker.say("a")
    try:
        assert active.wait(2)
        speaker.say("a")
        speaker.say_now("b")
        speaker.say_now("a")
        assert speaker.wait_idle(0.01) is False
        assert [e.state for e in events] == ["started"]
    finally:
        release.set()
    assert speaker.wait_idle(2) is True
    assert [(e.key, e.state, e.reason) for e in events] == [
        ("a", "started", None), ("a", "finished", None),
        ("a", "cancelled", "superseded"), ("b", "cancelled", "superseded"),
        ("a", "started", None), ("a", "finished", None),
    ]
    assert events[0].utterance_id == events[1].utterance_id
    assert events[4].utterance_id == events[5].utterance_id
    assert len({e.utterance_id for e in events}) == 4
    assert len(set(threads)) == 1
    assert threads[0] != threading.get_ident()


def test_missing_and_disabled_never_claim_playback(cfg):
    events = []
    speaker = Speaker(cfg, on_playback=events.append)
    speaker.say("missing")
    assert speaker.wait_idle(2)
    assert [e.state for e in events] == ["failed"]
    assert "missing.wav" in events[0].reason
    events.clear()
    silent = Speaker(cfg, enabled=False, on_playback=events.append)
    silent.say("a")
    assert silent.wait_idle(2)
    assert [(e.state, e.reason) for e in events] == [("cancelled", "disabled")]


def test_callback_can_enqueue_and_failure_does_not_kill_worker(cfg, monkeypatch):
    backend(monkeypatch, cfg)
    events = []

    def callback(event):
        events.append(event)
        if event.key == "a" and event.state == "finished":
            speaker.say("b")
            with pytest.raises(RuntimeError, match="callback"):
                speaker.wait_idle()
            raise ValueError("broken observer")

    speaker = Speaker(cfg, on_playback=callback)
    speaker.say("a")
    assert speaker.wait_idle(2)
    assert [(e.key, e.state) for e in events] == [
        ("a", "started"), ("a", "finished"), ("b", "started"), ("b", "finished")]


@pytest.mark.parametrize("aplay_code", [0, 3, None])
def test_alsa_success_failure_and_absent_backend(cfg, monkeypatch, aplay_code):
    backend(monkeypatch, cfg)
    monkeypatch.setitem(sys.modules, "sounddevice", None)
    monkeypatch.setattr("sonara.tts.shutil.which", lambda _: "aplay" if aplay_code is not None else None)

    class Process:
        def __init__(self, args): self.args = args
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def wait(self): return aplay_code

    monkeypatch.setattr("sonara.tts.subprocess.Popen", Process)
    events = []
    speaker = Speaker(cfg, on_playback=events.append)
    speaker.say("a")
    assert speaker.wait_idle(2)
    assert [e.state for e in events] == (
        ["failed"] if aplay_code is None else
        ["started", "finished" if aplay_code == 0 else "failed"])


def test_backend_failure_after_start_does_not_replay(cfg, monkeypatch):
    def fail():
        raise OSError("output disconnected")

    backend(monkeypatch, cfg, wait=fail)
    monkeypatch.setattr("sonara.tts.shutil.which", lambda _: pytest.fail("must not replay"))
    events = []
    speaker = Speaker(cfg, on_playback=events.append)
    speaker.say("a")
    assert speaker.wait_idle(2)
    assert [e.state for e in events] == ["started", "failed"]
