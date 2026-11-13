# Role brief: speech (Sommer-Lukas)

Own the files in the speech row of [../../AGENTS.md](../../AGENTS.md). The user explicitly
replaced the original neural-embedding plan with MFCC + DTW; do not restore OWW/Google embedding
weights, unrestricted ASR or recognition model selection.

## Current priorities

1. Maintain the NumPy MFCC frontend, banded DTW, conservative UNKNOWN rejection and versioned
   feature-only profiles in `sonara/models/`, `sonara/recognizer.py` and `sonara/audio/`.
2. Deliver the enrollment service and owner-scoped device/UI proposals in `roles/speech/integration/`.
   Do not edit device-owned controller/server/config/entry-point files; their owner integrates hooks.
3. Preserve Piper output and both PortAudio/explicit ALSA capture. The tested UNO Q USB headset is
   `alsa:plughw:CARD=Set,DEV=0`; `arecord`/`aplay` avoid the system PortAudio/sudo blocker.
4. Collect independent personal enrollment and held-out recordings when available. Never count
   enrollment self-matches or copies/augmentations as independent recognition accuracy.
5. Keep latency/rejection/memory measurements reproducible and label synthetic/corpus limitations.
   Public corpus helpers live in `roles/speech/evaluation/`; no corpus audio/weights are committed.

Current status, evidence and handoff: [STATUS.md](STATUS.md), [CONTRACT.md](CONTRACT.md),
[integration/README.md](integration/README.md), [README.md](README.md).

Nicla Voice remains a separately coordinated stretch trigger, not a replacement recognizer.
Defer it until the main MFCC + DTW workflow and device/UI integration are complete.

## Never

- Bypass the ownership hook or push changes to main.
- Change published interfaces without a CONTRACT update to the device owner.
- Commit raw user/corpus audio, model weights or credentials.
- Treat similarity as probability or report this small corpus diagnostic as patient accuracy.
- Dispatch a request from speech/enrollment; device confirmation remains mandatory.
