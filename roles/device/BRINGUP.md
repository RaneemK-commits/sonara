# UNO Q bring-up checklist (device)

Tick items as they pass and write down what you actually saw. Anything marked **VERIFY** is an
assumption from docs, not yet seen on our board.

## 1. Board and network
- [ ] Board: Arduino UNO Q 4GB. Debian on the Qualcomm MPU, STM32 MCU running the Arduino (Zephyr) core.
- [ ] Wi-Fi joined (same network as the caregiver phone). IP: `________` hostname: `________`
- [ ] SSH works: `ssh arduino@<ip>` (**VERIFY** default user).
- [ ] Clock is correct (`date`); request timestamps depend on it. No NTP offline → set once by hand.

## 2. Python app
- [ ] `python3 --version` ≥ 3.11 (**VERIFY**; else install or relax `pyproject.toml` via lead).
- [ ] `git clone` + `python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[audio,model]"`
- [ ] `python -m sonara --no-audio --mcu none` starts, `curl localhost:8000/api/health` → `ok: true`.
- [ ] From the phone: `http://<ip>:8000/caregiver` loads and connects (firewall/port open).
- [ ] Local `config/sonara.toml` on the board: `caregiver_token` changed (never committed), `bed_id` set.

## 3. Audio
- [ ] `arecord -l` shows the USB mic; `aplay -l` shows the speaker/USB audio out.
- [ ] `arecord -D <dev> -f S16_LE -r 16000 -c 1 -d 3 /tmp/t.wav && aplay /tmp/t.wav` (delete after; no audio kept).
- [ ] `python -c "import sounddevice as s; print(s.query_devices())"`; put the name/index in `audio.device`.
- [ ] Full flow with mic once speech's recognizer is ready: Talk → phrase spoken → confirm → caregiver.

## 4. Room display
- [ ] External display shows the desktop / a browser (**VERIFY** how the UNO Q drives it: USB-C dock/HDMI).
- [ ] Kiosk: `chromium --kiosk http://localhost:8000/room` (or whatever browser is installed).
- [ ] Touch input works on the room tiles (fallback when there is no mic).

## 5. MCU + Modulino Buttons
- [ ] Open question: Qwiic connector wired to the STM32 or to Linux I2C? Check board docs +
      `i2cdetect -l` / `i2cdetect -y <bus>` on Linux. Write the answer in STATUS.md Decisions.
- [ ] App Lab / `arduino-cli` can flash the sketch; an LED blink example runs.
- [ ] Bridge round-trip: sketch `Bridge.notify` reaches Python; Python `Bridge.call` reaches sketch
      (**VERIFY** names in `Arduino_RouterBridge` and `arduino.app_utils`).
- [ ] Modulino Buttons example runs (presses + LEDs), then the Sonara sketch.
- [ ] `python -m sonara --mcu unoq`: each button drives the controller; LEDs follow the state.

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
