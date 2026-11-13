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

### Additive Speaker playback lifecycle

```python
from sonara.tts import PlaybackEvent, Speaker
spk = Speaker(cfg, on_playback=on_playback)  # optional keyword-only callback
# on_playback(event: PlaybackEvent) runs on the speaker worker, not the device event loop.
```

Frozen events expose `utterance_id` (unique per say/say_now invocation), `key`, `state`
(`started`, `finished`, `failed`, `cancelled`) and optional `reason`. Existing `say(key)` and
`say_now(key)` signatures and None return values remain. `wait_idle(timeout=15.0)` now returns
True when the queue, active playback and callbacks have drained, False on timeout. Existing
callers can ignore the result; timeout neither cancels playback nor emits an event. Idle is
not evidence of successful playback. A concurrent later enqueue can make it busy again.

`started` follows successful `sounddevice.play()` or `aplay` process launch; it describes
backend start, not proof that sound reached a patient. `finished` follows backend completion.
Missing WAVs, unavailable backends, synthesis errors and nonzero aplay exits emit `failed`,
never `finished`. Failure before backend start has no `started`. Disabled output emits only
`cancelled` with reason `disabled`, so --no-audio never claims audible playback.

`say_now` does not interrupt active playback. Each dropped pending utterance gets exactly one
`cancelled` event with reason `superseded`, no start/finish. Cancellation delivery is serialized
after the active utterance completes and before the replacement starts. All callbacks run on
one worker outside speaker locks; they may enqueue speech. Callback exceptions are contained.
Keep callbacks short and use e.g. `loop.call_soon_threadsafe(handle_playback, event)` to transfer
to device's owning event loop. Do not mutate controller/UI state directly on the speaker thread.
Calling `wait_idle` from a callback raises RuntimeError rather than deadlocking the worker.
Device should match terminal events by utterance ID before clearing its active indicator.

Verification: `pytest -q tests/test_speech_playback.py tests/test_speech_recognition.py`.

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

## Experimental keyword-in-phrase contract (not activated)

The user's target is WATER/PAIN-like personal keywords inside longer phrases, rather than
classification of a whole phrase as though it were an isolated word. New speech-only APIs:

```python
from sonara.models.keywords import KeywordSpotter
spotter = KeywordSpotter.enroll({"WATER": clips, "PAIN": other_clips})
spotter.save(keyword_profile_directory)
spotter = KeywordSpotter.load(keyword_profile_directory)
spotter.scan(audio_window)  # <=5 s, returns KeywordEvent list, including rejections
spotter.feed(chunk)         # <=1 s chunks, bounded rolling buffer, synchronous worker call
spotter.reset()             # drop buffered audio / duplicate history on pause or dropped input
```

KeywordEvent has `start_s`, `end_s`, `observed_until_s`, `prediction` and `to_dict()`.
This requires fresh raw-MFCC references and shared enrollment scaling; existing CMVN templates
are rejected. Keyword profiles use keyword.json/references/, separate from active production
profiles. Existing Recognizer/AudioCapture APIs and controller behavior remain unchanged.

NEED for eventual device integration: shared microphone chunks on a bounded audio worker;
pause/reset for TTS, enrollment and AWAIT_CONFIRM; discard/reset on queue loss; request intents
only; accepted candidates enter existing confirmation, never direct caregiver dispatch. No
ambient keyword YES/NO confirmation. This is not ready to enable: real composed-speech trials
still reject all candidates, natural phrase accuracy and continuous negative calibration are
missing, and CPU real-time feasibility must be measured. See docs/KEYWORDS_IN_PHRASES.md.

The same persistent AudioCapture now exposes `read_chunk(timeout_s=.1)` (one float32 block or
None), with timeout bounded to 0–1 s, and monotonic `dropped_blocks`. It rejects reads during a
manual/VAD recording; the shared audio lock is still mandatory to serialize all consumers.
The keyword worker must compare the overrun counter before/after processing, discard results
on change, flush stale blocks and reset the detector. No new stream is opened automatically.
Fresh keyword enrollment trims only endpoints with 180 ms padding by default; callers can use
`trim_endpoints=False` for manual word boundaries. Existing enrollment/Recognizer behavior is
unchanged. `roles/speech/evaluation/evaluate_keyword_streams.py` measures annotated real WAV
streams, including event misses/false alarms, duplicate accepts and processing real-time factor.
