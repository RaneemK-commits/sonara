"""Fetch model weights ONCE, before the demo (the device itself then runs fully offline).

  python scripts/download_models.py

Downloads into models/:
  melspectrogram.onnx, embedding_model.onnx  — openWakeWord v0.5.1 release assets (Apache-2.0);
                                               the embedding net is Google's speech_embedding model
  en_US-lessac-medium.onnx(+.json)           — Piper voice from rhasspy/piper-voices (see its MODEL_CARD)

Record the exact URLs + SHA256 printed here in the README "Model provenance" section.
"""
from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

MODELS = Path(__file__).resolve().parent.parent / "models"
OWW = "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1"
PIPER = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium"
FILES = {
    "melspectrogram.onnx": f"{OWW}/melspectrogram.onnx",
    "embedding_model.onnx": f"{OWW}/embedding_model.onnx",
    "en_US-lessac-medium.onnx": f"{PIPER}/en_US-lessac-medium.onnx",
    "en_US-lessac-medium.onnx.json": f"{PIPER}/en_US-lessac-medium.onnx.json",
}


def main(only: list[str]) -> None:
    MODELS.mkdir(exist_ok=True)
    for name, url in FILES.items():
        if only and not any(o in name for o in only):
            continue
        out = MODELS / name
        if not out.exists():
            print(f"↓ {name}  ← {url}")
            urllib.request.urlretrieve(url, out)
        digest = hashlib.sha256(out.read_bytes()).hexdigest()
        print(f"  {name}: {out.stat().st_size / 1e6:.1f} MB  sha256={digest[:16]}…")


if __name__ == "__main__":
    main(sys.argv[1:])  # optional filters, e.g. `python scripts/download_models.py onnx`
