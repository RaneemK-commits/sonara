"""Persistent ALSA input for minimal Debian images without PortAudio."""
from __future__ import annotations

import shutil
import subprocess
import threading

import numpy as np


class ALSAInputStream:
    """Feed the existing audio queue from arecord, without temporary WAV files."""
    def __init__(self, sr: int, block: int, device: str, callback):
        executable = shutil.which("arecord")
        if executable is None:
            raise RuntimeError("install sounddevice/PortAudio or alsa-utils for microphone capture")
        self.command = [executable, "-q", "-D", device, "-t", "raw", "-f", "S16_LE",
                        "-c", "1", "-r", str(sr)]
        self.block, self.callback = block, callback
        self._started, self._stop = threading.Event(), threading.Event()
        self._error = ""
        self._process = None
        self._thread = None

    def start(self) -> None:
        self._process = subprocess.Popen(self.command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self._thread = threading.Thread(target=self._read, daemon=True, name="alsa-capture")
        self._thread.start()
        if not self._started.wait(2.) or self._error:
            self.close()
            raise RuntimeError(self._error or "ALSA microphone did not deliver audio")

    def _read(self) -> None:
        try:
            while not self._stop.is_set():
                data = self._process.stdout.read(self.block * 2)
                if len(data) != self.block * 2:
                    self._error = "ALSA microphone unavailable; check device name, permissions and format"
                    return
                audio = np.frombuffer(data, dtype='<i2').astype(np.float32) / 32768.
                self.callback(audio[:, None], self.block, None, None)
                self._started.set()
        finally:
            self._started.set()

    def stop(self) -> None:
        self._stop.set()
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=2.)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=2.)
        if self._thread is not None:
            self._thread.join(timeout=2.)

    def close(self) -> None:
        self.stop()
        if self._process is not None and self._process.stdout is not None:
            self._process.stdout.close()
