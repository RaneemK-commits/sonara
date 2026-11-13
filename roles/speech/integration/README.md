# NEED: device / UI / lead integration

Patches prepared against main `ac496e6` (which includes reboot recovery `ba13ef9` and Modulino LEDs
`3c6b11c`). The speech branch was then rebased onto `1abda6f`, preserving its new standalone
Arduino Router Bridge implementation; all three patches still apply cleanly. The speech branch changes **no device-owned or UI-owned production files**. Proposed
edits live here for their owners; the pre-commit ownership guard remains enabled.

## Device — exact hooks requested

Apply/adapt [device.patch](device.patch). It preserves `_recover_request_id()`, `_leds`,
`led_state()` and `mcu.set_leds(talk, confirm, cancel)` with string off/on/blink semantics.

`sonara/controller.py`:

- Add `audio_lock = threading.RLock()` and `enrollment_active = False`.
- `_on_talk`: acquire the shared lock without waiting; skip capture during enrollment.
- Always-on path: same lock/pause rule; recover cleanly after capture failure.
- Fixed recording: use `capture.record_manual(manual_duration_s)` when configured; otherwise
  retain VAD capture. Pass the matching `manual` flag to `Recognizer.recognize`.
- `room_state`: proposed additive `enrollment_active` boolean; `has_mic` is false while
  enrollment owns capture. Existing states/controls/request fields are preserved.
- Bound the action queue to 32 and keep enqueue nonblocking.
- Bind queued confirm actions to the current pending deadline; ignore an early/stale Send press
  so it cannot confirm a future/replaced recognition. Keep confirmation mandatory.
- Keep the controller thread handle, join on stop, and ignore unknown intent IDs safely.

`sonara/server/app.py`:

- Import `EnrollmentService` from `sonara.models.enrollment` and construct it once per app.
- Use synchronous route functions so capture/matching runs in FastAPI's worker pool.
- A shared operation wrapper acquires `controller.audio_lock` nonblocking (409 busy), maps
  invalid input/profile data to 422 and unavailable mic/runtime capture failure to 503.
- Keep normal `confirm`/`cancel` inputs; return 409 for `talk`/manual `select` during enrollment.
- Close capture during shutdown after stopping the controller.

| Method | Endpoint | Input / purpose |
|---|---|---|
| GET | `/api/profiles` | active ID, profile list, ready/error, counts, calibration, mic and intents |
| POST | `/api/enrollment/start` | `{profile_id, keep_audio:false}`; create/edit draft; pause recognition |
| POST | `/api/enrollment/intent` | `{intent}`; select configured intent |
| POST | `/api/enrollment/capture` | `{manual:true,seconds:3.0}`; device mic, stage one valid take |
| POST | `/api/enrollment/sample` | keep staged take; persist MFCCs and recalibrate |
| DELETE | `/api/enrollment/intents/{intent}` | replace intent by clearing its takes |
| DELETE | `/api/enrollment/intents/{intent}/samples/{index}` | delete a poor take |
| POST | `/api/enrollment/calibrate` | save draft thresholds and diagnostics |
| POST | `/api/enrollment/test` | capture/test draft; never invokes request pipeline |
| POST | `/api/enrollment/finish` | save/load selected profile; resume normal recognition |
| POST | `/api/enrollment/cancel` | discard pending take/close setup; resume recognition |
| POST | `/api/profiles/{profile_id}/load` | live profile switch |
| DELETE | `/api/profiles/{profile_id}` | delete profile and opt-in recordings |

`sonara/config.py`: **no edit or new hook required**. Existing Config/Intent/path helpers suffice.

`config/sonara.toml`:

- Remove `backend`, `matcher`, both embedding-model paths and legacy `threshold = 0.0`.
- Set profile ID/directory, band=0.2, margin=0.12. Omit threshold to use calibrated profile limits;
  explicitly setting zero rejects all. Old templates must be re-enrolled.
- Feature defaults: 16 kHz, 25/10 ms framing, FFT 512, Mel 40, MFCC 13, pre-emphasis .97,
  CMVN, variance floor .01. The profile stores its feature configuration.
- Add `manual_duration_s=0`, `min_rms=.00003`, `trim_factor=2`, `trim_pad_ms=180`;
  use 1200 ms trailing silence. Keep site-local device and token decisions with device.
- Verified board device: `alsa:plughw:CARD=Set,DEV=0` (USB headset/card 1).

`sonara/__main__.py`:

- Instantiate `Recognizer(cfg)` with no backend selection; remove obsolete backend CLI options.
- Make the recognizer available to enrollment even before a profile exists.
- Catch mic startup failures and preserve manual phrase tiles/no-audio startup.

## UI

[ui.patch](ui.patch) proposes the room onboarding dialog and a README update. The dialog uses
server-side device capture and requires five saved takes for each request before Finish. It
supports profile selection/deletion, repeating/clearing takes, calibration feedback and draft
recognition tests. Voice setup does not create caregiver requests. Preserve the current visual
work when adapting the patch; branding and phrase text remain UI-owned.

## Lead

[lead-dependencies.patch](lead-dependencies.patch) removes obsolete recognition ONNX/ASR extras,
retains Piper's TTS extra, and adds optional laptop-only corpus tools. Main README/design docs
still describe the old architecture until their owners integrate the scoped speech documentation.
Do not remove main's Modulino/Nicla sections when updating its design table.

Implementation notes and measured reports: [../README.md](../README.md),
[../docs/VALIDATION.md](../docs/VALIDATION.md), [../docs/CORPUS_EVALUATION.md](../docs/CORPUS_EVALUATION.md).
New dataset/synthetic helpers are under `roles/speech/evaluation/`, within speech ownership.

## Review and verify

In a disposable checkout of the speech branch, the corresponding owners can review/apply:

```bash
git apply --check roles/speech/integration/device.patch
git apply roles/speech/integration/device.patch
git apply roles/speech/integration/ui.patch
git apply roles/speech/integration/lead-dependencies.patch
python -m pytest -q tests roles/speech/integration/test_integrated_recognition.py
python -m sonara --no-audio --mcu none
```

`test_integrated_recognition.py` preserves the four real controller/server integration tests that
require these device hooks. They are intentionally outside default pytest collection on the
speech-only branch; the core EnrollmentService has an independent controller-contract test.
This separation does not remove the integration tests or claim that unmerged endpoints exist.

Do not apply the device patch over newer owner changes blindly: re-check its base and retain
reboot recovery, string LED semantics, delivery honesty and patient confirmation.
