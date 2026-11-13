# UNO Q bring-up checklist (device)

Tick items as they pass and write down what you actually saw. Anything marked **VERIFY** is an
assumption from docs, not yet seen on our board.

## 1. Board and network
- [ ] Board: Arduino UNO Q 4GB. Debian on the Qualcomm MPU, STM32 MCU running the Arduino (Zephyr) core.
- [x] Wi-Fi joined. IP `192.168.1.242` (DHCP, may change), hostname `OhmNoobsBoard` / `OhmNoobsBoard-3.local`.
- [x] SSH works: `ssh arduino@192.168.1.242` (user `arduino`, key auth set up from the dev laptop). Passwordless `sudo` is NOT available, so `apt install` needs the human.
- [x] Clock is correct (2026-11-13 UTC at probe time; checked, not NTP-proof offline) (`date`); request timestamps depend on it. No NTP offline → set once by hand.

## 2. Python app
- [x] Debian 13 (trixie) aarch64, Python 3.13.5, 3.6 GB RAM, rootfs 9.8 GB with only ~2.4 GB free (watch model/pip size). `python3-venv`/pip are NOT installed: used `python3 -m venv --without-pip` + `get-pip.py` (needs internet once; or `sudo apt install python3-venv python3-pip`).
- [x] Repo copied with `git archive HEAD | ssh … tar -x` into `~/sonara` (no git credentials on the board); `.venv` there, `pip install -e ".[dev,model,audio]"` OK. `pytest -q` = 12 passed on the board.
- [x] `python -m sonara --no-audio --mcu none` starts; `/api/health` → `ok: true` on the board and from the laptop over Wi-Fi.
- [x] `http://192.168.1.242:8000/caregiver` returns 200 from the laptop (no firewall in the way). [ ] Still to try from a phone, with a live WebSocket.
- [ ] Local `config/sonara.toml` on the board: `caregiver_token` changed (never committed), `bed_id` set.

## 3. Audio
- [x] `arecord -l` / `aplay -l`: card 1 `Set [USB Headphone Set]` (a USB headset, capture and playback) plus card 0 `ArduinoImolaHPH` (on-board codec). Set `audio.device` to the USB card. [ ] Record/playback test still to do.
- [ ] `arecord -D <dev> -f S16_LE -r 16000 -c 1 -d 3 /tmp/t.wav && aplay /tmp/t.wav` (delete after; no audio kept).
- [ ] **Blocked on sudo:** `import sounddevice` fails with `PortAudio library not found` → needs `sudo apt install libportaudio2`.
- [ ] `python -c "import sounddevice as s; print(s.query_devices())"`; put the name/index in `audio.device`.
- [ ] Full flow with mic once speech's recognizer is ready: Talk → phrase spoken → confirm → caregiver.

## 4. Room display
- [ ] **Speaker: NOT working (2026-11-13), parked.** Creative Pebble V2 has no USB audio (USB-C is power only); its 3.5 mm plug is in the touch display's jack, so audio must go over DisplayPort.
  - Board side: DP audio is `hw:ArduinoImolaHPH,3` (MultiMedia4). UCM `Qualcomm/qcm2290/HDMI.conf` enables `SEC_MI2S_RX Audio Mixer MultiMedia4` (I2S to the anx7625 DP bridge); `DISPLAY_PORT_RX Audio Mixer MultiMedia4` is the wrong control (with it on, hw_params fails) and the two are mutually exclusive. UCM `HiFi.conf` lists "HDMI support" as a TODO.
  - Result: playback with `SEC_MI2S_RX` on succeeds (rc 0) but the human hears only static, for tones and prompts alike. One clean tone was heard once (16:04, after `alsaucm -c 0 set _verb HDMI set _enadev HDMI`) and could not be reproduced.
  - Something resets `SEC_MI2S_RX` to off over time (probably WirePlumber restoring the HiFi verb).
  - Board-local leftovers: `~/.asoundrc` (default playback → plug to hw:...,3 at 48 kHz stereo, capture → USB mic). Remove it if a USB audio output is used instead.
  - Recommended fix: a USB audio adapter with a 3.5 mm output (class-compliant, `snd-usb-audio`) for the Pebble, or a USB speaker. Then point `~/.asoundrc` playback at that card.
- [ ] External display: board shows `card0-DP-1` under `/sys/class/drm`, session is xfce4 on tty. `chromium` is installed. Still to confirm the display is lit.
- [ ] Kiosk: `chromium --kiosk http://localhost:8000/room` (or whatever browser is installed).
- [ ] Touch input works on the room tiles (fallback when there is no mic).

## 5. MCU + Modulino Buttons
- [x] I2C scan (human ran it with sudo, 2026-11-13): bus 0 (Geni-I2C) empty; bus 1 (Geni-I2C) only kernel-owned `UU` addresses (0x2a 0x2c 0x38 0x39 0x3d 0x3f 0x42 0x58, board internals), nothing at 0x3E. A Modulino Buttons is therefore NOT visible to Linux, so the Qwiic connector belongs to the STM32: **buttons are read by the sketch via Arduino_Modulino**, as already written. Caveat: not confirmed that the Buttons module was plugged in during the scan; re-scan if in doubt. `i2cdetect` needs `sudo` and is in `/usr/sbin`.
- [ ] (older note) `/dev/i2c-0`, `i2c-1`, `i2c-2` exist on Linux; `i2cdetect` is not installed (`sudo apt install i2c-tools`). `arduino-router` is running (Bridge). Open question: Qwiic connector wired to the STM32 or to Linux I2C? Check board docs +
      `i2cdetect -l` / `i2cdetect -y <bus>` on Linux. Write the answer in STATUS.md Decisions.
- [ ] App Lab / `arduino-cli` (installed at `/usr/bin/arduino-cli`; `~/ArduinoApps` has `blink-from-mpu`, `reading-accelerometer-data`) can flash the sketch; an LED blink example runs.
- [x] **Modulino Buttons work (2026-11-13):** sketch compiles for `arduino:zephyr:unoq` against Arduino_Modulino 0.10.0 + Arduino_RouterBridge 0.4.4, flashed via a throwaway App Lab app (`~/ArduinoApps/sonara-buttons-test`; its sketch.yaml needs the full lib list copied from `blink-from-mpu`, else VL53L4CD headers are missing). Presses talk/confirm/cancel all arrived in Python via Bridge. LED echo from a handler failed: nested Bridge calls inside a provided handler are not allowed (controller never does this). MCU→Linux **notify works**; **Python→MCU `set_leds` still to verify**.
- [ ] Plain-venv Bridge: `arduino.app_utils` only exists inside App Lab containers. Use `pip install arduino-router-bridge` (`arduino.router_bridge.Bridge`). Socket `/var/run/arduino-router.sock` is `root:arduino-router 660` and `arduino` is not in that group: needs `sudo usermod -aG arduino-router arduino` + re-login. Stop the test app first (it also provides `button`).
- [ ] (older) Bridge round-trip: sketch `Bridge.notify` reaches Python; Python `Bridge.call` reaches sketch
      (**VERIFY** names in `Arduino_RouterBridge` and `arduino.app_utils`).
- [ ] Modulino Buttons example runs (presses + LEDs), then the Sonara sketch.
- [x] `python -m sonara --no-audio --mcu unoq` (2026-11-13): room-tile WATER → Confirm button → `QUEUED` → Cancel button → `CANCELLED`, both with actor `patient`. LED states per step: confirmed by eye for the echo test; full-flow LED pattern still to confirm by eye.
- [x] Root cause of earlier "no presses": `app stop` of the test app left the MCU's Bridge dead (LEDs frozen, no events). Fix: keep `user:sonara-mcu` running, `arduino-app-cli properties set default user:sonara-mcu` (start on boot, **reboot not yet tested**).
- Deploy `mcu/`: `tar -cf - -C mcu . | ssh arduino@<ip> 'tar -xf - -C ~/ArduinoApps/sonara-mcu'` then `arduino-app-cli app restart user:sonara-mcu`.

## 6. Run on boot
- [ ] systemd unit (or App Lab app) starts Sonara and the kiosk after power-on; `Restart=on-failure`.
- [ ] Power-cycle test: open request survives, status still honest.

## Measured numbers (fill in; label measured vs estimated)
| What | Value | How |
|---|---|---|
| Boot → app ready | | stopwatch |
| Button press → LISTENING on screen | | metrics / video |
| Confirm → caregiver screen DISPLAYED | | metrics |
| Idle / active power | | USB power meter |

## Needs the human (no sudo for the agent)
```bash
sudo apt install -y libportaudio2 i2c-tools python3-venv python3-pip   # done
sudo usermod -aG arduino-router arduino                                 # then log out/in
```

## Speaker + start on boot (2026-11-13, working)
- **Speaker works.** Cause of the static/silence: PipeWire/WirePlumber had the UNO Q card on the `HiFi` profile
  (headphone/lineout only). Fix: `HDMI` profile → sink "HDMI Digital Stereo Output" (`hw:ArduinoImolaHPH,3`,
  route `SEC_MI2S_RX Audio Mixer MultiMedia4`, set by the profile) → display over HDMI → display 3.5 mm jack → Creative Pebble V2.
  Ignore `DISPLAY_PORT_RX` (wrong control). PipeWire negotiates S24_LE 48 kHz itself.
- `sudo apt install -y pipewire-alsa` so ALSA programs (Sonara's Speaker, aplay) go through PipeWire. Old `~/.asoundrc` removed (backup `~/.asoundrc.sonara-hw-backup`).
- WirePlumber does not remember the profile across reboots: pinned with `roles/device/deploy/51-sonara-hdmi.conf`.
- ALSA card numbers swap between boots (USB mic was card 1, now 0): always use card **names**, never `-c 0`.
- Start on boot: `roles/device/deploy/sonara.service` (systemd user unit, linger already on) + `sonara-room.desktop` (kiosk autostart). Reboot 1: MCU app, Sonara, kiosk came back; audio did not (fixed with the WirePlumber rule). Reboot 2: see below.

## Performance (2026-11-13, evening)
- Lag report: room page idle costs chromium 114-136% + Xorg 22-26% + xfwm4 18% of one core (of 4). Cause: `web/shared/orb.js` 60 fps rAF loop forever (ui, NEED posted). Sonara itself 1.4%.
- Done on board: xfwm4 compositing off (`DISPLAY=:0 xfconf-query -c xfwm4 -p /general/use_compositing -s false`, persists): xfwm4 18% -> 0%.
- Second, intermittent load: USB mic `xhci-hcd: WARN: buffer overrun event for slot 5 ep 4` ~10/s, CPU0 98% IRQ. Gone when Sonara's continuous `arecord` stops; did not reappear after restart (trigger unknown, FYI to speech). Kernel console loglevel is 7; lowering it (`kernel.printk = 3 4 1 3` in /etc/sysctl.d, sudo) is a possible mitigation, not yet tested.
- Boot race: sometimes the ADSP publishes no APR services, sound card missing ("deferred probe pending", lpass-lpi-pinctrl clk 'audio'). ADSP restart fixes it: `roles/device/deploy/sonara-audio-check.service` (needs sudo install).
