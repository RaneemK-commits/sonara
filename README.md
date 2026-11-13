# Sonara — giving every voice a way through

An **offline bedside personal speech translator** on the Arduino UNO Q. A patient with a speech
impairment says a phrase *in their own way*. Sonara recognises it on the device with a
personalised neural speech model and **speaks it aloud in clear English**. If the caregiver isn't
in the room, Sonara sends the request to their phone and tells the patient honestly whether it was
seen, acknowledged and completed.

No cloud, no LLM, no raw audio leaves the board. Prototype only, **not a medical device** and not
a replacement for a nurse-call system.

- Design decisions: [docs/DESIGN.md](docs/DESIGN.md) · Original PDR: [docs/PDR_v1.0.md](docs/PDR_v1.0.md)

> **Status: scaffold only.** The room display and caregiver dashboard in `web/` are functional
> placeholders for wiring up the flow. **UI design and branding are not decided yet.** Full
> speech/audio integration still needs verification. The Modulino Buttons → Bridge → Sonara path
> has been verified on the UNO Q.

## How it works
```
USB mic → VAD → log-mel → speech-embedding CNN (ONNX, frozen) → DTW vs patient's prototypes
       → accept / reject → Piper voice (pre-synthesised) → room speaker + room display
       → [confirm] → SQLite → WebSocket → caregiver dashboard → ack/complete → spoken back
MCU (STM32): Talk / Confirm / Cancel buttons + 3 status LEDs over Arduino Bridge
```
| Path | What |
|---|---|
| `sonara/models/` | MFCC features, neural embedder, DTW, few-shot prototype classifier |
| `sonara/audio/` | mic capture, VAD, WAV I/O |
| `sonara/controller.py` | bedside state machine (listen → speak → confirm → dispatch) |
| `sonara/store.py` | request status machine with honesty rules (SQLite) |
| `sonara/server/` | FastAPI + WebSocket server |
| `web/room/` | patient-facing room display (external screen) |
| `web/caregiver/` | caregiver dashboard (phone/laptop on local Wi-Fi) |
| `mcu/` | Always-on App Lab app; STM32 buttons/LED sketch at `mcu/sketch/sketch.ino` |
| `scripts/` | model download, TTS pre-generation, enrollment, evaluation, benchmark |

## Quick start (laptop, UI only — no mic needed)
```bash
python -m venv .venv && .venv/Scripts/activate      # Linux/UNO Q: source .venv/bin/activate
pip install -e ".[dev,audio,model]"
python -m sonara --no-audio --mcu none
```
Open http://localhost:8000/room and http://localhost:8000/caregiver (token: `caregiver_token`
in `config/sonara.toml`). Tap a phrase tile → Send → acknowledge on the dashboard.

## Full pipeline
```bash
python scripts/download_models.py                 # once, while online: embedding net + Piper voice
pip install piper-tts && python scripts/pregenerate_tts.py
python scripts/enroll.py --takes 5 --keep-audio --speaker alice   # 5 takes per phrase
python -m sonara                                  # t / c / x + Enter = Talk / Confirm / Cancel
```
On the UNO Q: set `[hardware] mcu = "unoq"`, the audio `device`, change `caregiver_token`, then open
`localhost:8000/room` full-screen on the external display.

## Evaluation (the numbers for the pitch)
```bash
python scripts/evaluate.py data/recordings/alice --enroll 3 --systems oww-dtw oww-mean mfcc-dtw asr --simulated
python scripts/benchmark.py --wav data/recordings/alice/WATER/<file>.wav --idle-watts X --active-watts Y
```
`asr` = Whisper-tiny + keyword matching (`pip install faster-whisper`): what a standard
recogniser does with the same atypical speech. Put `_UNKNOWN/*.wav` (other speech, coughs,
noise) in the dataset to measure false accepts. Label acted recordings `--simulated`.

## Tests
```bash
pytest -q
```

## Team split (24 h)
| Who | Owns |
|---|---|
| Speech | `sonara/models`, `scripts/enroll.py`, `scripts/evaluate.py`: recordings, thresholds, results table |
| Backend | `sonara/store.py`, `sonara/server`, `sonara/controller.py`: reliability, reconnect, reset |
| Frontend | `web/room`, `web/caregiver`: kiosk mode, alerts, error states |
| Hardware | `mcu/`, `sonara/hw/mcu.py`, USB audio on UNO Q, power meter, `scripts/benchmark.py` |

## Model provenance
- Speech embedding: Google `speech_embedding` model as exported by openWakeWord v0.5.1 (Apache-2.0)
- Mel front-end: openWakeWord `melspectrogram.onnx` v0.5.1
- TTS voice: Piper `en_US-lessac-medium` (rhasspy/piper-voices; check its model card for license)

Record the SHA256 values printed by `download_models.py` here.

## Privacy and safety
- Enrollment stores embeddings only. WAVs are kept only with `--keep-audio`, locally, for consented evaluation.
- Only `{request_id, bed_id, intent, status, timestamps}` crosses the LAN.
- `DISPLAYED` requires a caregiver-screen receipt. `ACKNOWLEDGED` requires a caregiver click.
  No receipt → patient is told the request has **not** reached anyone.
- Reset: `POST /api/reset` (token) deletes request history. Delete `data/profiles/` to remove templates.

## License
MIT
