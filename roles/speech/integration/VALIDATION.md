# Handoff verification

Final branch base: `1abda6f` from origin/main, including device reboot recovery, Modulino string
LEDs and the standalone Arduino Router Bridge implementation. Proposal context base: `ac496e6`;
all three proposals still pass apply checks after the rebase.

- Speech-only branch: **54 passed in 5.04 s** (`pytest -q`). Current main's device tests are included.
- Disposable combined checkout with device.patch, ui.patch and lead-dependencies.patch applied:
  **58 passed in 7.45 s** (`python -m pytest -q tests roles/speech/integration/test_integrated_recognition.py`).
- All three review patches pass `git apply --check` against the declared base.
- Controller/server/config/entry point, UI production HTML, root README and pyproject.toml are
  unchanged on the speech branch. The ownership hook is enabled with role speech.
- Combined verification preserves `_recover_request_id`, `led_state` and string LED arguments.
- Four endpoint/controller-dependent tests remain available in the integration module, alongside
  independent speech/model/audio/service tests collected normally.

Historical hardware evidence remains under ../docs/validation: the earlier fully integrated
validation checkout passed 53 tests on both laptop and UNO Q; its microphone/API/Piper tests
and corpus experiments used the isolated /tmp deployment, not the device agent's ~/sonara.
Current branch tests were rerun after adapting to latest main; owner integration is still required
for enrollment endpoints and the proposed room_state field to exist in production.

No recordings, voice weights or patient profiles are included in this branch. Generated patch
files contain ordinary unified-diff context lines; whitespace checks exclude *.patch and pass
for all executable source/test/documentation content.
