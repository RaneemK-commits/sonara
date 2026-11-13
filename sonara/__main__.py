"""Run the Sonara bedside device: `python -m sonara [--no-audio]`."""
from __future__ import annotations

import argparse

import uvicorn

from .config import load_config
from .controller import Controller
from .hw.mcu import make_mcu
from .server.app import create_app
from .server.hub import Hub
from .store import RequestStore
from .tts import Speaker


def main() -> None:
    ap = argparse.ArgumentParser(prog="sonara")
    ap.add_argument("--config", default=None)
    ap.add_argument("--no-audio", action="store_true",
                    help="no mic/speaker: drive the flow from the room screen tiles (UI dev)")
    ap.add_argument("--mcu", choices=["keyboard", "unoq", "none"])
    ap.add_argument("--port", type=int)
    args = ap.parse_args()

    cfg = load_config(args.config)
    srv = cfg.section("server")
    store = RequestStore(cfg.path(srv.get("db_path", "data/sonara.db")))
    hub = Hub()
    speaker = Speaker(cfg, enabled=not args.no_audio)
    mcu = make_mcu(args.mcu or cfg.section("hardware").get("mcu", "keyboard"))

    from .recognizer import Recognizer
    recognizer, capture = Recognizer(cfg), None
    if not recognizer.ready:
        print("[recognition] enroll a voice profile in /room; phrase tiles are available")
    if not args.no_audio:
        from .audio.capture import AudioCapture
        a = cfg.section("audio")
        try:
            capture = AudioCapture(a.get("sample_rate", 16000), a.get("block_ms", 30), a.get("device"),
                               a.get("max_utterance_s", 5.0), a.get("silence_end_ms", 700),
                               a.get("speech_start_factor", 3.0), a.get("min_speech_ms", 200))
        except Exception as exc:  # Includes device-specific PortAudio errors.
            print(f"[audio] microphone unavailable: {exc}; phrase tiles remain available")

    controller = Controller(cfg, store, hub, speaker, mcu, recognizer, capture)
    app = create_app(cfg, store, hub, controller)
    port = args.port or srv.get("port", 8000)
    print(f"Sonara {cfg.bed_id}: room http://localhost:{port}/room  "
          f"caregiver http://<board-ip>:{port}/caregiver")
    uvicorn.run(app, host=srv.get("host", "0.0.0.0"), port=port, log_level="warning")


if __name__ == "__main__":
    main()
