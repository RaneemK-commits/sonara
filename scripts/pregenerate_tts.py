"""Synthesise every fixed output sentence with Piper into assets/tts/<key>.wav.

  pip install piper-tts && python scripts/pregenerate_tts.py [--force]

Run on the UNO Q itself too, to report on-device TTS synthesis time (printed per sentence).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sonara.config import load_config  # noqa: E402
from sonara.tts import synthesize_to_wav  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    cfg = load_config()
    t = cfg.section("tts")
    voice = cfg.path(t.get("voice_model"))
    out_dir = cfg.path(t.get("prompt_dir", "assets/tts"))
    texts = {i.id: i.speak for i in cfg.intents} | cfg.prompts
    total = 0.0
    for key, text in texts.items():
        out = out_dir / f"{key}.wav"
        if out.exists() and not args.force:
            continue
        t0 = time.perf_counter()
        synthesize_to_wav(voice, text, out)
        dt = time.perf_counter() - t0
        total += dt
        print(f"{key:18s} {dt * 1000:7.0f} ms  {text}")
    print(f"done — {total:.1f} s total synthesis")


if __name__ == "__main__":
    main()
