# Role brief: speech (Sommer-Lukas)

You own turning audio into an intent, and playing fixed sentences back. Files: see the ownership table in [../../AGENTS.md](../../AGENTS.md).

**Goal:** a personalised, on-device recogniser that is *visibly better than standard ASR* on impaired
speech, honestly measured, and cheap enough in energy to score well on SCI.

## Priorities
1. Run `scripts/download_models.py` and get `OWWEmbedder` working (it's untested). Check the ONNX input/output shapes.
2. Pre-generate TTS WAVs with Piper (`scripts/pregenerate_tts.py`).
3. Record team takes for the demo phrases (`enroll.py --keep-audio`, labelled simulated). Tune threshold and margin.
4. TORGO evaluation per speaker on its command words: `oww-dtw` vs `mfcc-dtw` vs `asr` (Whisper-tiny). See [docs/DATASETS.md](../../docs/DATASETS.md).
5. On-board latency benchmark (`scripts/benchmark.py`) and the per-stage numbers for SCI ([docs/SCI.md](../../docs/SCI.md)).

## Never
- Change `Prediction`, `Recognizer`, `Speaker` or `AudioCapture` signatures without a `CONTRACT` post.
- Commit audio, model weights or TORGO files.
- Return a guessed intent when below threshold. Rejection is a feature.
