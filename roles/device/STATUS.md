# device STATUS

Live backlog for the `device` agent. Update before you stop so a fresh session can resume.

## New device agent intake (2026-11-13)
- Implementation commit `5add73c` pushed to main after explicit human approval. Human installed the replacement audio-check from `/home/arduino/sonara-audio-check.service`. Verified installed file matches, systemd validation passes, unit enabled, `NeedDaemonReload=no`, Sonara active. Recovery behavior on the next boot remains untested.
- Read role instructions, STATUS, CONTRACT, BRINGUP, device runtime and board history through the prior handoff; posted online FYI (issue comment 6864076740).
- Checkout is main at 57d0280. Use session-local `SONARA_ROLE=device`: clone git role is still lead. Existing `.claude/launch.json` and `learning/` changes belong to the human and were left untouched.
- Speech branch d0e2810 keyword detector is explicitly not ready to enable; fresh enrollment and recognition reliability remain speech work.
- Intake validation: `python -m pytest -q tests/test_device.py` under system Python 3.14 produced no output and was interrupted; no passing result claimed. Diagnose test environment before implementation/push.
- No runtime changes or board deployment during intake. Next work remains the ordered backlog below.

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
0. Louder phone chime: human explicitly authorized this one UI edit/deployment. Applied only beep() on live caregiver page (three longer alternating tones, gain .65, guarded/awaited audio resume); served code and JS syntax verified. Refreshed phone listening test pending. `web/caregiver/index.html` is modified locally but intentionally not committed under device role; owning UI agent should commit `integration/louder-phone-alert.patch` against current main. Device-only patch/docs handoff can be pushed without bypassing ownership hook. Backend suite remains 75 passed.
0. Latest demo feedback: human verified phone bell + new-request alert audible, spoken acknowledgment and Resolve/history worked for simulated req-0006. Now requests much louder phone alert. Prepared `integration/louder-phone-alert.patch` for UI (peak gain .2→.65, three longer alternating tones, awaits audio resume; JS syntax checked). Not applied to UI or deployed: human previously left UI edits to UI agent, and automatic approval review usage limit blocked further remote actions. Physical cancel/reboot tests remain incomplete.
0. Latest human steering: use friend's Android/Chrome for demo, skip local-CA phone setup. Optional push disabled in board-local config and HTTPS proxy stopped/disabled; keep standard HTTP :8000 dashboard + foreground bell. Preserve push implementation for later. No locked-phone delivery test completed; UI/lead informed to defer that setup. Authoritative display and Safari auth fixes remain live.
0. Web Push: human approved optional internet-enabled generic alerts. Backend + authoritative display now deployed; HTTPS proxy at `https://192.168.1.242:8443/caregiver` verified with local CA. `data/local.toml` has push enabled, VAPID key local 0600, zero subscriptions initially. Public certificate download `/sonara-demo-ca.crt` verified. Human phone certificate trust and UI Home Screen/permission integration pending; real locked-phone delivery NOT yet tested. 75 full tests passed on isolated UNO Q. Safari disconnection resolved after browser-visible 4401 auth fix; human confirmed connected. No request data in push payload, no delivery-driven status changes.
0. User requested end-to-end state-driven feedback after missing rejection screen. Device now implements additive authoritative `room_state.display` (see FLOW.md/CONTRACT.md), unique attempt/outcome IDs, explicit five-second feedback, server expiry publication, expired-confirm/busy-input guards. UI integration patch prepared at `integration/room-display.patch` (`git apply --check` passes); human explicitly left applying it to UI agent. Speech NEED requests true playback callbacks. Full isolated UNO Q suite: 63 passed, one Starlette deprecation warning; four focused regressions pass locally. Handoff branch `codex/device-room-state`; not live-deployed. Branch also includes prior audio-check correction in 4d12032, whose reinstallation remains pending.
1. DONE: human installed updated `deploy/sonara-audio-check.service`; file match, systemd validation, enabled state and daemon reload verified. Adds PipeWire restart after ADSP recovery and ELD warning. Actual recovery on next boot remains untested; do not run recovery unnecessarily against live audio.
2. DONE: default config loading merges git-ignored `data/local.toml`; explicit `--config` stays self-contained. Deployed loader and migrated board mic/device duration/token to mode-0600 local file. Verified tracked defaults + overrides exactly equal existing settings; no token logged. Live service not restarted.
3. Phase 3 reliability: live no-caregiver and phone reconnect tests PASSED on 2026-11-13: human pressed B for WATER, req-0004 QUEUED at 20:44:44 UTC → NOT_DISPLAYED at 20:44:54 UTC; human verified C fast blink and not-reached feedback. Actual caregiver-screen receipt at 20:47:31 UTC → DISPLAYED; caregiver click at 20:47:38 → ACKNOWLEDGED (human heard speaker feedback); Resolve at 20:47:46 → COMPLETED. Verified server event log. Power-cut mid-request remains untested.
4. Watch the USB mic overrun storm (CPU0 98% IRQ, stalls audio): restart Sonara clears it; root fix is speech opening capture only on Talk.
5. Stretch: Modulino Distance; Nicla trigger (with speech).

## Known pitfalls (see BRINGUP.md)
- ADSP sometimes publishes no audio services at boot → no sound card. ADSP restart fixes it, but then PipeWire must restart and the **HDMI cable must be replugged** (ELD lost). Never toggle the display with `xrandr --off`: screen stays dark until a replug.
- `pkill -f <pattern>` over ssh kills its own shell if the pattern appears later in the same command: run kills in a separate ssh call.
- `arduino-app-cli app stop` kills the MCU's Bridge link; keep `user:sonara-mcu` running.
- ALSA card numbers swap between boots: use card names.

## Needs from others
- ui: Web Push worker `web/sw.js`, manifest `web/manifest.webmanifest`, subscribe/unsubscribe Home Screen flow. Device routes/API ready; POST/DELETE require X-Sonara-Token. Human is doing local CA trust setup. Backend is live, but real locked-phone push requires UI + subscription.
- lead: optional `push` dependency extra and documented human-approved offline exception requested. Installed pywebpush 2.5.0 manually on board meanwhile.
- speech: lifecycle hook delivered on speech/playback-lifecycle @ 2bf9b02; integration follows current phone-alert work.
- ui: integrate `roles/device/integration/room-display.patch` (authoritative display selection; repeated rejection; pending intent; no guessed playback pill). Human explicitly left this edit to UI. Existing public fields preserved.
- speech: additive started/finished/failed playback events needed to complete truthful speaking state; no implementation guessed in device.
- ui: human requested more discoverable caregiver history on phone. Existing collapsed Recent history shows completed/cancelled rows; NEED posted with existing API support and no contract change required.
- speech: live recognition rejects every attempt (numbers in the board NEED); open the mic only on Talk (USB overrun storm).
- ui: apply speech's `roles/speech/integration/ui.patch` (voice-setup screen) against device CONTRACT; enrollment is CLI-only until then.

## Published
- c1482f4 `mcu/` App Lab app; f4ca596 + f157554 speech integration + CONTRACT (enrollment endpoints, `room_state.enrollment_active`); ad4fec2 + 78bd032 deploy files.

## Decisions
- 2026-11-13: live board ELD exposes `monitor_name`, not `eld_valid`; corrected staged audio-check predicate accordingly (present/empty/missing fixtures pass), added TimeoutStartSec=150 for three recovery attempts. Corrected unit staged at `~/sonara-audio-check.service`, systemd validation passes; requires reinstall after earlier version. Recent boot brought Sonara and local overrides back; five-minute kernel sample had zero USB overruns.
- 2026-11-13 (new device agent): use already ignored `data/local.toml` for scalar/top-level section overrides; malformed TOML fails instead of silently reverting credentials. Local-only backup is `data/config-before-local.toml` (0600).
- 2026-11-13 validation: full suite on UNO Q isolated `/tmp/sonara-device-validation`: 55 passed, one Starlette deprecation warning; no-audio startup health passed on port 8019. Device reboot test now reopens an on-disk SQLite DB. Physical phone reconnect/LED observation/power cut remain unverified. Windows test hang traced to Python 3.14 asyncio socketpair creation before app startup; config-only test passes locally.
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
