# Speech contract: MFCC + DTW

User-authorized replacement: MFCC is the only production frontend. No recognition model download,
ONNX embedding runtime, unrestricted ASR or cloud service is used. Device integration landed on main through `f4ca596`/`f157554`; the original
[integration handoff](integration/README.md) remains available for reference.

```python
from sonara.recognizer import Recognizer
rec = Recognizer(cfg)                     # production constructor
rec = Recognizer(cfg, None)               # temporary calling compatibility with main's entry point
rec.backend == "mfcc"                     # fixed identifier, not a model selector
rec.ready                                # bool; false for absent/corrupt/empty selected profiles
rec.recognize(audio, manual=False)        # Prediction; invalid audio returns a rejected Prediction
rec.reload(profile_id)                    # atomic live load, remembers active profile
rec.embed(audio, manual=False)            # float32 (T, 39) or None for invalid audio
```

The optional legacy constructor argument accepts only `None` or `"mfcc"`; selecting `"oww"`
raises a descriptive ValueError. The device entry-point patch removes its obsolete backend CLI.
No neural compatibility path remains. Remove this temporary argument once device callers migrate.

`Prediction.intent` is an intent ID or None. `accepted` is false for UNKNOWN. `best` can be None
on invalid input/empty profiles and is for diagnostics only. Existing `score`, `distance`,
`margin`, `threshold` and `scores` remain; `latency_ms` and `reason` are additive. Display closeness
is not probability. `to_dict()` maps nonfinite diagnostic values to JSON null.

Input: 16 kHz mono finite float32, nominal range [-1, 1], 0.3–5 seconds. Heavy clipping, silence,
DC-only and invalid recordings reject. `manual=True` preserves explicit recording boundaries;
it does not bypass recording-quality checks. PCM WAV conversion helpers live in `sonara/audio/`.

```python
from sonara.audio.capture import AudioCapture
cap = AudioCapture(device="alsa:plughw:CARD=Set,DEV=0")  # verified USB headset on UNO Q
cap.flush()
cap.record_utterance(wait_s=4.0)           # float32 mono or None
cap.record_manual(seconds=3.0)            # bounded 0.3–5 s capture on the same stream
cap.close()

from sonara.tts import Speaker
spk.say(key); spk.say_now(key); spk.wait_idle(timeout=15.0)
```

Existing AudioCapture/Speaker method signatures remain. The ALSA adapter uses installed
`arecord`; Piper playback falls back to `aplay` without PortAudio. No sudo/libportaudio2 is needed
for this explicit device path. The device worker must serialize capture with enrollment.

Profiles now use `data/profiles/<profile_id>/{metadata.json,templates.npz}`, with `active.txt`
in the parent directory. They contain MFCC templates, feature configuration, counts, matching
parameters, thresholds and calibration diagnostics. Old embedding profiles require re-enrollment.
Raw retention is an explicit opt-in; deletion removes retained recordings as well.

## Enrollment service and required device hooks

```python
from sonara.models.enrollment import EnrollmentService
service = EnrollmentService(cfg, controller)
```

The controller supplies `recognizer`, `capture`, `speaker`, `state`, `enrollment_active`, and
`_publish()`. The device/API adapter owns a shared `audio_lock` and calls service operations
under it. The service publishes profile/progress/test data only; it never dispatches a request.
All endpoints and the proposed additive `room_state.enrollment_active` field are described in
[integration/README.md](integration/README.md). Existing Talk/Confirm/Cancel meanings remain.
The device owner publishes the HTTP/WebSocket contract after integrating its owned files.

**Threshold migration:** remove legacy `threshold = 0.0` from sonara.toml to use profile limits.
An explicitly configured zero now safely rejects all; it never disables rejection. The current
old config therefore remains fail-closed until the device config proposal is integrated.

## Voice pipeline follow-up (additive, no device API changes)

Batched DTW preserves scores and rejection settings. AudioCapture maintains bounded idle-energy
history to initialize VAD; existing capture signatures and the shared audio lock still apply.
An explicit failed `reload(profile_id)` now preserves the prior patient and raises ValueError;
a corrupt currently selected profile fails closed. Profile IDs must match their directory.
Evaluation RSS is null where Unix/Linux measurement is unavailable. No controller, server,
configuration, speaker-routing or button changes are needed for this follow-up.

Rejection diagnostics use Python logger `sonara.recognizer`, WARNING for rejection and INFO
for acceptance. The process stderr/log stream contains best label, distance, threshold, actual
and required margin, frames, template count, processing milliseconds and reason. No raw audio
or template arrays are logged. New calibration `status`/`loo_gap_p10`/`required_margin` fields
are additive; no threshold is relaxed. CLI enrollment prints actionable calibration reasons.
