"""Speech output: plays pre-synthesised Piper WAVs (assets/tts/<key>.wav).

Keys are intent IDs (e.g. "WATER") and prompt names (e.g. "acknowledged"). All outputs are fixed
sentences, so they are synthesised once with scripts/pregenerate_tts.py — still fully offline
neural TTS, but zero synthesis latency at runtime. Playback runs on its own thread so the
controller never blocks on audio.
"""
from __future__ import annotations

import queue
import shutil
import subprocess
import threading
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


class Speaker:
    def __init__(self, cfg: Config, enabled: bool = True):
        t = cfg.section("tts")
        self.cfg = cfg
        self.dir = cfg.path(t.get("prompt_dir", "assets/tts"))
        self.voice = cfg.path(t.get("voice_model", "models/en_US-lessac-medium.onnx"))
        self.live = t.get("allow_live_synthesis", False)
        self.enabled = enabled
        self.texts = {i.id: i.speak for i in cfg.intents} | cfg.prompts
        self._q: queue.Queue[str] = queue.Queue()
        threading.Thread(target=self._worker, daemon=True, name="speaker").start()

    def say(self, key: str) -> None:
        """Queue a phrase for playback (non-blocking)."""
        self._q.put(key)

    def say_now(self, key: str) -> None:
        """Clear pending phrases, then speak this one (e.g. a new recognition result)."""
        while not self._q.empty():
            self._q.get_nowait()
        self._q.put(key)

    _playing = False

    def wait_idle(self, timeout: float = 15.0) -> None:
        """Block until nothing is playing or queued (so the mic doesn't hear the speaker)."""
        import time

        end = time.monotonic() + timeout
        while (self._playing or not self._q.empty()) and time.monotonic() < end:
            time.sleep(0.05)

    def _worker(self) -> None:
        while True:
            key = self._q.get()
            self._playing = True
            try:
                with METRICS.time("tts_play"):
                    self._play(key)
            except Exception as e:  # never crash the device over audio output
                print(f"[tts] {key}: {e}")
            finally:
                self._playing = False

    def _play(self, key: str) -> None:
        text = self.texts.get(key, key)
        print(f"[speak] {text}")
        if not self.enabled:
            return
        wav = self.dir / f"{key}.wav"
        if not wav.exists():
            if not self.live:
                print(f"[tts] missing {wav.name}; run scripts/pregenerate_tts.py")
                return
            with METRICS.time("tts_synth_live"):
                synthesize_to_wav(self.voice, text, wav)
        try:
            import sounddevice as sd

            audio, sr = read_wav(wav, max_seconds=None)
            sd.play(audio, sr)
            sd.wait()
        except (ImportError, OSError):  # Minimal Debian may lack the PortAudio shared library.
            if shutil.which("aplay"):
                subprocess.run(["aplay", "-q", str(wav)], check=False)
