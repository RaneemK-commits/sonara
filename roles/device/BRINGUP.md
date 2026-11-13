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
- [ ] External display: board shows `card0-DP-1` under `/sys/class/drm`, session is xfce4 on tty. `chromium` is installed. Still to confirm the display is lit.
- [ ] Kiosk: `chromium --kiosk http://localhost:8000/room` (or whatever browser is installed).
- [ ] Touch input works on the room tiles (fallback when there is no mic).

## 5. MCU + Modulino Buttons
- [ ] `/dev/i2c-0`, `i2c-1`, `i2c-2` exist on Linux; `i2cdetect` is not installed (`sudo apt install i2c-tools`). `arduino-router` is running (Bridge). Open question: Qwiic connector wired to the STM32 or to Linux I2C? Check board docs +
      `i2cdetect -l` / `i2cdetect -y <bus>` on Linux. Write the answer in STATUS.md Decisions.
- [ ] App Lab / `arduino-cli` (installed at `/usr/bin/arduino-cli`; `~/ArduinoApps` has `blink-from-mpu`, `reading-accelerometer-data`) can flash the sketch; an LED blink example runs.
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

## Needs the human (no sudo for the agent)
```bash
sudo apt install -y libportaudio2 i2c-tools python3-venv python3-pip
```
