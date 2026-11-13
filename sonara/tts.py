"""Speech output: plays pre-synthesised Piper WAVs (assets/tts/<key>.wav).

Keys are intent IDs (e.g. "WATER") and prompt names (e.g. "acknowledged"). All outputs are fixed
sentences, so they are synthesised once with scripts/pregenerate_tts.py — still fully offline
neural TTS, but zero synthesis latency at runtime. Playback runs on its own thread so the
controller never blocks on audio.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import shutil
import subprocess
import threading
from typing import Callable, Literal
from uuid import uuid4
from pathlib import Path

from .audio.wavio import read_wav
from .config import Config
from .metrics import METRICS


def synthesize_to_wav(voice_model: Path, text: str, out_path: Path) -> None:
    """Synthesise one sentence with Piper (python package `piper-tts`)."""
    import wave

    from piper import PiperVoice  # type: ignore

    voice = PiperVoice.load(str(voice_model))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as wf:
        if hasattr(voice, "synthesize_wav"):  # piper-tts >= 1.3
            voice.synthesize_wav(text, wf)
        else:  # piper-tts 1.2
            voice.synthesize(text, wf)


@dataclass(frozen=True)
class PlaybackEvent:
    utterance_id: str
    key: str
    state: Literal["started", "finished", "failed", "cancelled"]
    reason: str | None = None


class Speaker:
    def __init__(self, cfg: Config, enabled: bool = True, *,
                 on_playback: Callable[[PlaybackEvent], None] | None = None):
        t = cfg.section("tts")
        self.cfg = cfg
        self.dir = cfg.path(t.get("prompt_dir", "assets/tts"))
        self.voice = cfg.path(t.get("voice_model", "models/en_US-lessac-medium.onnx"))
        self.live = t.get("allow_live_synthesis", False)
        self.enabled = enabled
        self.texts = {i.id: i.speak for i in cfg.intents} | cfg.prompts
        self._condition = threading.Condition()
        self._pending: deque[PlaybackEvent] = deque()
        self._playing = False
        self._on_playback = on_playback
        self._current: PlaybackEvent | None = None
        self._thread = threading.Thread(target=self._worker, daemon=True, name="speaker")
        self._thread.start()

    def say(self, key: str) -> None:
        """Queue a phrase for playback (non-blocking)."""
        with self._condition:
            self._pending.append(PlaybackEvent(uuid4().hex, key, "started"))
            self._condition.notify()

    def say_now(self, key: str) -> None:
        """Cancel pending phrases; leave active playback running, then speak key."""
        with self._condition:
            self._pending = deque(
                PlaybackEvent(e.utterance_id, e.key, "cancelled", "superseded")
                if e.state == "started" else e for e in self._pending
            )
            self._pending.append(PlaybackEvent(uuid4().hex, key, "started"))
            self._condition.notify()

    def wait_idle(self, timeout: float = 15.0) -> bool:
        """True once playback and event delivery drain; False on timeout, without cancellation.

        Do not call from a playback callback, which executes on the speaker worker.
        """
        if threading.current_thread() is self._thread:
            raise RuntimeError("wait_idle cannot run in a playback callback")
        with self._condition:
            return self._condition.wait_for(
                lambda: not self._playing and not self._pending, timeout=max(0.0, timeout)
            )

    def _emit(self, event: PlaybackEvent) -> None:
        # One worker serializes all callbacks; no speaker lock is held during user code.
        if self._on_playback is not None:
            try:
                self._on_playback(event)
            except Exception as exc:
                print(f"[tts] playback callback: {exc}")

    def _started(self) -> None:
        if getattr(self, "_current", None) is not None:
            self._emit(self._current)

    def _worker(self) -> None:
        while True:
            with self._condition:
                self._condition.wait_for(lambda: bool(self._pending))
                event = self._pending.popleft()
                self._playing = True
            self._current = event
            try:
                if event.state == "cancelled":
                    self._emit(event)
                elif not self.enabled:
                    self._emit(PlaybackEvent(event.utterance_id, event.key, "cancelled", "disabled"))
                else:
                    with METRICS.time("tts_play"):
                        self._play(event.key)
                    self._emit(PlaybackEvent(event.utterance_id, event.key, "finished"))
            except Exception as exc:  # never crash the device over audio output
                print(f"[tts] {event.key}: {exc}")
                self._emit(PlaybackEvent(event.utterance_id, event.key, "failed", str(exc)))
            finally:
                self._current = None
                with self._condition:
                    self._playing = False
                    self._condition.notify_all()

    def _play(self, key: str) -> None:
        text = self.texts.get(key, key)
        print(f"[speak] {text}")
        if not self.enabled:
            return
        wav = self.dir / f"{key}.wav"
        if not wav.exists():
            if not self.live:
                raise FileNotFoundError(f"missing {wav.name}; run scripts/pregenerate_tts.py")
            with METRICS.time("tts_synth_live"):
                synthesize_to_wav(self.voice, text, wav)
        started = False
        try:
            import sounddevice as sd

            audio, sr = read_wav(wav, max_seconds=None)
            sd.play(audio, sr)
            started = True
            self._started()
            sd.wait()
        except (ImportError, OSError):  # Minimal Debian may lack the PortAudio shared library.
            if started:
                raise  # A failed active backend must not replay the phrase on another one.
            if not shutil.which("aplay"):
                raise RuntimeError("No audio backend available (PortAudio or aplay)")
            with subprocess.Popen(["aplay", "-q", str(wav)]) as process:
                self._started()
                code = process.wait()
                if code:
                    raise subprocess.CalledProcessError(code, process.args)
