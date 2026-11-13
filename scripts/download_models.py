"""Download only the Piper voice for offline output speech; recognition needs no weights."""
from __future__ import annotations

import hashlib
import os
import tempfile
import sys
import urllib.request
from pathlib import Path

MODELS = Path(__file__).resolve().parent.parent / "models"
PIPER = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium"
FILES = {
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
            with tempfile.NamedTemporaryFile(dir=MODELS, delete=False) as handle:
                temporary = Path(handle.name)
            try:
                urllib.request.urlretrieve(url, temporary)
                os.replace(temporary, out)
            finally:
                temporary.unlink(missing_ok=True)
        digest = hashlib.sha256(out.read_bytes()).hexdigest()
        print(f"  {name}: {out.stat().st_size / 1e6:.1f} MB  sha256={digest[:16]}…")


if __name__ == "__main__":
    main(sys.argv[1:])  # optional filters, e.g. `python scripts/download_models.py onnx`
