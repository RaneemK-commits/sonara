# device STATUS

Live backlog for the `device` agent. Update before you stop so a fresh session can resume.

## Where things stand (2026-11-13, 19:55 UTC, handoff)
Full system runs on the UNO Q at `ssh arduino@192.168.1.242` (DHCP; fallback `OhmNoobsBoard-3.local`), main @ 78bd032.
Details, commands and pitfalls: [BRINGUP.md](BRINGUP.md). Deploy files: [deploy/](deploy/). `pytest -q` passes (Windows: skip the two speech files that `import resource`).

| Piece | State on the board |
|---|---|
| State machine, store, server/WS (`sonara/controller.py`, `store.py`, `server/`) | works; speech enrollment hooks + CONTRACT integrated (f4ca596, f157554) |
| Modulino Buttons A=Talk B=Confirm C=Cancel + LEDs (`mcu/` App Lab app, `sonara/hw/mcu.py`) | **works**; `user:sonara-mcu` is the default app (starts on boot); Sonara owns the Bridge `button` route via `arduino-router-bridge` |
| Speaker: Creative Pebble on the display's 3.5 mm jack via HDMI/DP audio | **works**; PipeWire HDMI profile pinned by `deploy/51-sonara-hdmi.conf`, `pipewire-alsa` installed, volume 0.8 |
| Start on boot | `deploy/sonara.service` (user unit, enabled, linger on), `deploy/sonara-room.desktop` (kiosk), `deploy/sonara-audio-check.service` (root, enabled) |
| Mic | USB mic `alsa:plughw:CARD=Set,DEV=0` works for capture |
| Voice recognition | **rejects everything** live; handed to speech (board NEED, 2026-11-13) |
| Caregiver token | random, board-local `config/sonara.toml` only |

Board-local edits to `~/sonara/config/sonara.toml` (re-apply after every sync, since `git archive` overwrites them):
`device = "alsa:plughw:CARD=Set,DEV=0"`, `manual_duration_s = 3.0`, `caregiver_token = <board value>`.
Sync code to the board: `git archive --format=tar HEAD | ssh arduino@192.168.1.242 'tar -xf - -C ~/sonara'`, then re-apply the above, then `systemctl --user restart sonara`.

## Next (in order)
1. Install the updated `deploy/sonara-audio-check.service` (adds the ELD warning; copied to /tmp on the board, needs sudo): `sudo cp /tmp/sonara-audio-check.service /etc/systemd/system/ && sudo systemctl daemon-reload`.
2. Board-local config override so syncs stop clobbering mic/token (e.g. a git-ignored `config/local.toml` merged by `config.py`; device owns `config.py`).
3. Phase 3 reliability, live: caregiver phone drop/reconnect → DISPLAYED; no caregiver → NOT_DISPLAYED + C fast blink (never seen by eye: every test pressed C before 10 s); power-cut mid-request.
4. Watch the USB mic overrun storm (CPU0 98% IRQ, stalls audio): restart Sonara clears it; root fix is speech opening capture only on Talk.
5. Stretch: Modulino Distance; Nicla trigger (with speech).

## Known pitfalls (see BRINGUP.md)
- ADSP sometimes publishes no audio services at boot → no sound card. ADSP restart fixes it, but then PipeWire must restart and the **HDMI cable must be replugged** (ELD lost). Never toggle the display with `xrandr --off`: screen stays dark until a replug.
- `pkill -f <pattern>` over ssh kills its own shell if the pattern appears later in the same command: run kills in a separate ssh call.
- `arduino-app-cli app stop` kills the MCU's Bridge link; keep `user:sonara-mcu` running.
- ALSA card numbers swap between boots: use card names.

## Needs from others
- speech: live recognition rejects every attempt (numbers in the board NEED); open the mic only on Talk (USB overrun storm).
- ui: apply speech's `roles/speech/integration/ui.patch` (voice-setup screen) against device CONTRACT; enrollment is CLI-only until then.

## Published
- c1482f4 `mcu/` App Lab app; f4ca596 + f157554 speech integration + CONTRACT (enrollment endpoints, `room_state.enrollment_active`); ad4fec2 + 78bd032 deploy files.

## Decisions
- 2026-11-13: LEDs follow the Modulino plan in DESIGN.md — Talk on while listening; Confirm blinks
  while a phrase waits for confirmation; Cancel on while a sent request can still be cancelled,
  and **blinks fast while it is `NOT_DISPLAYED`** (keeps the honest "not reached anyone" signal at the hand).
- 2026-11-13: Confirm LED blinks slow (400 ms), Cancel blinks fast (150 ms) so the two blinks are distinguishable.
- 2026-11-13: Active requests ordered by `created_at, request_id` (second-resolution timestamps tie).
- 2026-11-13: Qwiic/Modulino is on the STM32 side (no 0x3E on Linux I2C buses 0/1): MCU sketch reads the buttons, Python only gets Bridge events. Caveat: Buttons module may not have been plugged in during the scan.
- 2026-11-13: `arduino-app-cli app stop` kills the sketch's Bridge link (sketch keeps looping, no RPC either way). So `mcu/` is an App Lab app that stays running as the board's default app; its Python is empty and Sonara (outside App Lab, `arduino-router-bridge`) owns the `button` route.
- 2026-11-13: Plan lives in this file plus `BRINGUP.md`; no new code modules until hardware forces them.
- 2026-11-13: Sonara runs as a systemd user unit (PipeWire lives in the user session); kiosk via XDG autostart.
- 2026-11-13: Speaker path = PipeWire HDMI profile → DP → display jack. `SEC_MI2S_RX Audio Mixer MultiMedia4` is the real route; `DISPLAY_PORT_RX` is wrong.
- 2026-11-13: xfwm4 compositing off on the board (saved 18% of a core).
