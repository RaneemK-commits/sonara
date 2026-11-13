# device STATUS

Live backlog for the `device` agent. Update before you stop so a fresh session can resume.

## Where things stand (2026-11-13)
The software slice exists and runs on a laptop: `python -m sonara --no-audio` → room tiles →
confirm → caregiver ack/complete. `pytest -q` = 12 passed (8 device).
Nothing has touched real hardware yet. Hardware checklist: [BRINGUP.md](BRINGUP.md).

| Piece | File | State |
|---|---|---|
| State machine | `sonara/controller.py` | works (IDLE/LISTENING/PROCESSING/AWAIT_CONFIRM, confirm timeout, cancel) |
| Request store | `sonara/store.py` | works (SQLite, honest transitions, event log) |
| Server + WS | `sonara/server/app.py`, `hub.py` | works (API per CONTRACT.md, NOT_DISPLAYED watchdog, snapshot replay) |
| MCU bridge (Linux) | `sonara/hw/mcu.py` | keyboard + null work; `UnoQBridgeMCU` **unverified** |
| MCU sketch | `mcu/sonara_mcu/sonara_mcu.ino` | Modulino Buttons version, **not compiled or flashed yet** |
| Entry point / config | `sonara/__main__.py`, `config.py`, `config/sonara.toml` | works |

## Plan (in order; top open item = what to do next)

### Phase 0 — laptop, no hardware — DONE (uncommitted until pushed)
- [x] Reboot recovery: `Controller` restores `request_id` from the newest active request for this
      bed at construction, so room screen, LEDs and Cancel survive a restart.
- [x] LED model → Modulino semantics: `led_state(state, status)` in `controller.py`;
      `set_leds(talk, confirm, cancel)` each `"off"|"on"|"blink"`, sent to the MCU only on change.
      `mcu.py` (all three classes) and the sketch (now Modulino Buttons, codes 0/1/2) updated together.
- [x] Tests: LED mapping, LEDs through select→confirm→cancel, reboot recovery (other beds ignored),
      receipt after `NOT_DISPLAYED` on caregiver reconnect. `pytest -q` = 12 passed.
- [ ] `ACK` the speech contract once speech posts its embedder `DONE`; use `--no-audio` until then.

### Phase 1 — UNO Q bring-up (as soon as the board is on the desk) — see BRINGUP.md
- [ ] Board on Wi-Fi, SSH in, note IP + hostname; Python ≥3.11 venv; `pip install -e ".[audio,model]"`.
- [ ] `python -m sonara --no-audio --mcu none` on the board; open `/room` on the external display
      and `/caregiver` from a phone on the same Wi-Fi. **First end-to-end on hardware.**
- [ ] USB mic + speaker visible to ALSA (`arecord -l`, `aplay -l`); set `audio.device`.
- [ ] Kiosk browser on the external display pointing at `http://localhost:8000/room`.
- [ ] Autostart (systemd unit or App Lab app, whichever the board supports) + restart on crash.
- [ ] `FYI` to speech: board is up, how to SSH/run `scripts/benchmark.py` there.

### Phase 2 — Modulino Buttons (core challenge requirement)
- [ ] **Answer the open question:** does the Qwiic connector reach the STM32 (sketch reads via
      `Arduino_Modulino`) or Linux (`/dev/i2c-*`)? Check with an App Lab example + `i2cdetect`.
- [ ] MCU path (expected): sketch uses `ModulinoButtons`, sends `Bridge.notify("button", name)`,
      provides `set_leds(talk, confirm, cancel)`; blink timing done on the MCU.
- [ ] Verify `UnoQBridgeMCU` against the real Bridge API names; reconnect if the router restarts.
- [ ] Debounce + ignore holds (one press = one event); measure button → LISTENING latency.

### Phase 3 — reliability (what makes the demo "run without luck")
- [ ] Caregiver phone drops Wi-Fi → reconnect → snapshot replay → receipt → `DISPLAYED` (test it live).
- [ ] No caregiver screen → `NOT_DISPLAYED` spoken + Cancel LED blinking within `display_timeout_s`.
- [ ] Mic unplugged / no recognizer → fall back to room tiles, never crash the loop.
- [ ] Pull the power mid-request → reboot → request still listed and still honest.
- [ ] `caregiver_token` set only in the board's local config (not in git).
- [ ] Per-stage latency in `/api/metrics` (button, record, recognize, TTS start, dispatch).

### Phase 4 — stretch (only after 1–3 are solid)
- [ ] Modulino **Distance**: presence for N ms → `caregiver_nearby` (skip "Send to caregiver?"),
      hand-wave → `talk`, display dim / model idle when nobody near (measured SCI comparison).
- [ ] Nicla Voice integration: its trigger arrives as a `talk` event in `sonara/hw/mcu.py`
      (speech owns `nicla/`; agree the transport — UART/USB serial — with speech first).
- [ ] USB power meter readings for SCI (labelled measured), with speech.

## Needs from others
- speech: `DONE` when `Recognizer` + `AudioCapture` + `Speaker` work, so the mic path can be tested on the board.
- ui: nothing yet. Will post `CONTRACT` if `room_state` gains fields (e.g. `caregiver_nearby`).

## Published
- (commits other roles can rely on)

## Decisions
- 2026-11-13: LEDs follow the Modulino plan in DESIGN.md — Talk on while listening; Confirm blinks
  while a phrase waits for confirmation; Cancel on while a sent request can still be cancelled,
  and **blinks fast while it is `NOT_DISPLAYED`** (keeps the honest "not reached anyone" signal at the hand).
- 2026-11-13: Confirm LED blinks slow (400 ms), Cancel blinks fast (150 ms) so the two blinks are distinguishable.
- 2026-11-13: Active requests ordered by `created_at, request_id` (second-resolution timestamps tie).
- 2026-11-13: Qwiic/Modulino is on the STM32 side (no 0x3E on Linux I2C buses 0/1): MCU sketch reads the buttons, Python only gets Bridge events. Caveat: Buttons module may not have been plugged in during the scan.
- 2026-11-13: Plan lives in this file plus `BRINGUP.md`; no new code modules until hardware forces them.
