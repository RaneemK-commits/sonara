# Speech STATUS

## Now

- MFCC + DTW implementation ready on `speech/mfcc-enrollment`, based on main `ac496e6`.
- NEED device integration: exact hooks and a current-main proposal in `integration/README.md`
  and `integration/device.patch`. Device-owned production files are unchanged in this branch.
- NEED UI/lead: review `integration/ui.patch`, `integration/lead-dependencies.patch` and scoped docs.
- Recognition code, audio capture, playback, profile storage and template enrollment service are
  implemented. Endpoint/controller/UI proposals remain pending their owners' integration.

## Verified

- Before ownership handoff: 53 tests passed on both laptop and owner UNO Q; current-main speech-only
  and proposed integrated checks are recorded in integration/VALIDATION.md before push.
- USB headset works with ALSA `plughw:CARD=Set,DEV=0`; no PortAudio/sudo needed for that path.
- Piper generated 16 prompts; board `aplay` accepted the Listening WAV with matching checksum.
- Short synthetic 25-template processing: board mean 298 ms / p95 351 ms. Five-second stress: ~4.1 s.
- Public German corpus: four complete single-take references; 40 independent five-second UNKNOWN
  windows, zero observed false accepts on laptop and board. Mean ~83 ms / ~1.19 s respectively.
- Corpus lacks repeated phrases and speaker IDs; held-out personalized intent accuracy is unmeasured.

## Board isolation

- Other agent's `~/sonara` and port 8000 were not changed.
- Speech validation copy is `/tmp/sonara-mfcc-validation`; temporary onboarding instance used
  port 8012, separate profiles. The validation directory is not a persistent deployment.
- No patient recording, public corpus WAV, model weight, token or generated playback WAV is committed.

## Decisions

- User explicitly requested MFCC-only recognition; neural selection/download paths removed from
  speech code. Device/lead proposals remove the remaining legacy CLI/config/dependency entries.
- Preserve existing device reboot/Modulino work; publish owner-scoped integration patches rather
  than edit their production files. Do not merge or force-push main.
- Keep a transitional `Recognizer(cfg, None)` calling form and fixed `backend="mfcc"` identifier
  so the old entry point can call speech code while device migrates.
- Explicit zero thresholds reject all. The old config must drop its zero sentinel before normal
  recognition; its old templates cannot be converted into MFCC templates.
- Core enrollment service moved to speech-owned `sonara/models/enrollment.py`; helper tools and
  documentation moved under `roles/speech/` to honor the ownership hook.
- User will copy the hub message. No external board comment is posted automatically.
