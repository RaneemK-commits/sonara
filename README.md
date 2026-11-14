<p align="center">
  <img src="assets/logo.png" alt="Sonara" width="315">
</p>

<p align="center"><b>Giving every voice a way through.</b></p>

An **offline bedside personal speech translator** on the Arduino UNO Q. A patient with a speech
impairment says a phrase *in their own way*. Sonara recognises it on the device from that
person's own enrolled sound patterns and **speaks it aloud in clear English**. After the patient
confirms, the request goes to the caregiver's phone, and Sonara tells the patient honestly whether
it was seen, acknowledged and completed.

No cloud, no LLM, no raw audio leaves the board. Prototype only: **not a medical device** and not
a replacement for a nurse-call system.

- Design decisions: [docs/DESIGN.md](docs/DESIGN.md) · Original PDR: [docs/PDR_v1.0.md](docs/PDR_v1.0.md)
- Branding as shipped: [roles/ui/BRANDING.md](roles/ui/BRANDING.md) · Environmental scoring: [docs/SCI.md](docs/SCI.md)

> **Status (2026-11-14): working end to end on the UNO Q.** Talk, spoken phrase, confirmation,
> caregiver phone alert, acknowledge and complete all run on the board. Known limits:
> - Recognition is a **personal, few-example matcher**. The live demo uses a supervised
>   closest-label mode (distance gate, no margin): wrong guesses must be cancelled by the patient,
>   and it is not robust at rejecting similar-sounding words. Numbers are small personal
>   development results, not general accuracy ([roles/speech/STATUS.md](roles/speech/STATUS.md)).
> - Voice YES / NO is **off** on the live profile. Confirm and Cancel are the physical buttons or touch.
> - Recognition takes several seconds on the board's CPU.
> - Phone alerts work while the dashboard is open. Locked-phone Web Push is built but not live.

## How it works
```
Modulino Talk (A) → USB mic → VAD / fixed window → MFCC (+ delta, CMVN)
   → banded DTW vs the patient's own templates → accept / reject (distance and margin gates)
   → pre-synthesised Piper voice speaks it → room display shows it
   → Confirm (B) → SQLite → WebSocket → caregiver dashboard → acknowledge / complete → spoken back
MCU (STM32): Modulino Buttons A Talk · B Confirm · C Cancel, with three status LEDs, over Arduino Bridge
```
The state machine is `IDLE → LISTENING → PROCESSING → AWAIT_CONFIRM`. It always returns to idle,
ignores presses made while it is busy, and never sends a request nobody confirmed.

| Path | What |
|---|---|
| `sonara/models/` | MFCC features, DTW, personal templates, enrollment, keyword experiments |
| `sonara/audio/` | mic capture, VAD, WAV I/O |
| `sonara/recognizer.py`, `sonara/tts.py` | audio in → `intent + score` or rejection; pre-synthesised Piper prompts |
| `sonara/controller.py` | bedside state machine and the `display` the room screen renders |
| `sonara/store.py` | request status machine with the honesty rules (SQLite) |
| `sonara/server/` | FastAPI + WebSocket server, optional Web Push |
| `sonara/hw/mcu.py` | Modulino buttons and LEDs over Arduino Bridge (laptop stand-ins included) |
| `web/room/` | patient screen on the external touch display: the Sonara orb, one message per screen, A/B/C legend |
| `web/caregiver/` | nurse dashboard (phone, local Wi-Fi): requests, acknowledge, resolve, per-patient history |
| `mcu/` | App Lab app; STM32 sketch `mcu/sketch/sketch.ino` |
| `config/` | `sonara.toml` (runtime), `intents.toml` (the five phrases and the words spoken for them) |
| `scripts/` | model download, TTS prompts, enrollment, evaluation, benchmark |
| `roles/` | per-role briefs, live status and published contracts |
| `tools/` | team message board and file-ownership hook ([tools/README.md](tools/README.md)) |

**Phrases:** Help, Water, Food, Pain, Bathroom (plus Yes and No answers).

## Patient screen and buttons
One message per screen, set by the device: ready, listening, thinking, confirm, sending, notified,
acknowledged, plus the plain answers *Yes*, *No*, *Okay, not sent* and *Request cancelled*, and the
failure screens *I didn’t understand* and *Unable to notify your nurse*. The legend under the text
always shows what **A Talk**, **B Confirm**, **C Cancel** do right now, and greys out the rest.
"Your nurse has been notified" appears only after the nurse's screen has really shown the request.

## Run it yourself

### 1. Laptop, UI only (no mic, no hardware)
Needs Python 3.11+.
```bash
git clone https://github.com/RaneemK-commits/sonara.git && cd sonara
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ".[dev,audio]"
python -m sonara --no-audio --mcu none
```
Open http://localhost:8000/room (patient screen) and http://localhost:8000/caregiver (nurse; token is
`caregiver_token` in `config/sonara.toml`). With no mic the room shows phrase tiles: tap one, confirm,
then acknowledge and resolve on the caregiver page. `python -m sonara --mcu keyboard` adds `t` / `c` / `x`
+ Enter for Talk / Confirm / Cancel. Check everything with `pytest -q`.

### 2. Laptop with a microphone: your own voice
```bash
pip install -e ".[audio,tts]"
python scripts/download_models.py            # once, online: the Piper voice
python scripts/pregenerate_tts.py            # writes the spoken prompts to assets/tts/*.wav
python scripts/enroll.py --takes 5 --keep-audio     # say each phrase 5 times
python -m sonara --mcu keyboard
```
Press `t` + Enter, say a phrase within the recording window, then `c` + Enter to confirm. Enrollment
stores MFCC features only; `--keep-audio` also keeps your WAVs (local, git-ignored) for evaluation.
Other enrollment options: `--profile NAME`, `--intents WATER PAIN`, `--replace`, `--delete-intent X`,
`--from-dir DIR` (import WAVs). Voice setup is also exposed over `/api/enrollment/*`.

### 3. On the Arduino UNO Q
Hardware: UNO Q 4 GB, Modulino Buttons on Qwiic, USB microphone, speaker, external display.
1. **Code.** The board has no git credentials, so push the tree over ssh:
   `git archive --format=tar HEAD | ssh arduino@<board-ip> 'tar -xf - -C ~/sonara'`.
   On the board: `python3 -m venv .venv && .venv/bin/pip install -e ".[audio,tts]" arduino-router-bridge`.
2. **Prompts and voice.** `assets/tts/*.wav` and the Piper voice are git-ignored, so run
   `download_models.py` and `pregenerate_tts.py` on the board (needs internet once) or copy those folders over.
3. **Voice profile.** Enroll on the board (`scripts/enroll.py`) or copy a profile into `data/profiles/`.
4. **Local settings** in `~/sonara/data/local.toml` (git-ignored, survives code syncs):
   ```toml
   [audio]
   device = "alsa:plughw:CARD=Set,DEV=0"   # use the card NAME, numbers swap between boots
   manual_duration_s = 3.0                 # fixed recording window after Talk
   [server]
   caregiver_token = "<something-random>"
   [hardware]
   mcu = "unoq"
   ```
5. **Buttons.** Copy `mcu/` to `~/ArduinoApps/sonara-mcu`, then
   `arduino-app-cli app start user:sonara-mcu` and `arduino-app-cli properties set default user:sonara-mcu`.
   Keep it running: stopping the app drops the button link.
6. **Service.** `cp roles/device/deploy/sonara.service ~/.config/systemd/user/ && systemctl --user daemon-reload && systemctl --user enable --now sonara`.
   Logs: `journalctl --user -u sonara -f`. Each button press is logged as `[mcu] button talk|confirm|cancel`.
7. **Display and speaker.** Open `http://localhost:8000/room` full-screen (see `roles/device/deploy/sonara-room.desktop`).
   Speaker audio goes through the display's jack; the WirePlumber file is in `roles/device/deploy/`.
8. **Phones.** Open `http://<board-ip>:8000/caregiver` on the same Wi-Fi.

Everything board-specific, with the pitfalls we hit (audio route, USB overruns, changing IPs):
[roles/device/BRINGUP.md](roles/device/BRINGUP.md).

### Configuration
| File | What |
|---|---|
| `config/sonara.toml` | defaults: `[audio]`, `[recognition]`, `[features]`, `[tts]`, `[flow]`, `[server]`, `[hardware]`, `[push]` |
| `data/local.toml` | per-machine overrides, merged section by section; ignored when you pass `--config` |
| `config/intents.toml` | phrases: id, label, spoken sentence, whether it can be sent to a caregiver |

CLI: `python -m sonara [--config FILE] [--no-audio] [--mcu keyboard|unoq|none] [--port N]`.
Useful `[flow]` keys: `confirm_timeout_s` (a waiting phrase is dropped, never sent), `listen_on_confirm`
(hear a spoken yes/no while a phrase waits; needs YES/NO enrolled), `result_feedback_s`.

## Technical documentation

### Architecture
One Python process (`python -m sonara`) owns everything except the button hardware:

```
 STM32 sketch (mcu/) --Bridge.notify("button")--> hw/mcu.py ---+
   Modulino Buttons + LEDs <--set_leds--                       v
 USB mic -> audio/capture.py -> recognizer.py            controller.py (one thread, one queue)
                               (MFCC + DTW)  <---------  state machine, speaks via tts.py
                                                               | display + request events
                       store.py (SQLite, status rules) <-------+
                                  |
                       server/app.py (FastAPI) -- WebSocket hub --> /room (patient), /caregiver (nurse)
```
- **Speech decides *what* was said, device decides *what happens*.** The recognizer returns an intent
  and score or a rejection and knows nothing about requests. The controller never second-guesses a rejection.
- **The controller is the only writer.** Buttons, HTTP input and recognizer results all become queued
  events handled in order by one thread, so the room screen, LEDs and database cannot disagree.

### Recognition
16 kHz mono audio, 0.3 to 5 s, validated (clipping, silence, DC offset). Features: 13 MFCCs with deltas
and accelerations (39 dimensions per frame), CMVN. Matching: banded DTW against the patient's enrolled
templates, averaging the two nearest per intent. A result is accepted only if the best distance is
under the threshold (calibrated leave-one-out at enrollment) **and** the runner-up is far enough
behind (margin). Otherwise it is UNKNOWN and the patient is asked to repeat. Templates are personal,
so the input can be any language, dialect or vocalisation; output is always the fixed English sentence.
Contract: [roles/speech/CONTRACT.md](roles/speech/CONTRACT.md) · evidence and limits:
[roles/speech/docs/](roles/speech/docs/).

### State machine and display
States: `IDLE`, `LISTENING`, `PROCESSING`, `AWAIT_CONFIRM`. A recognised phrase is spoken at once, then
waits for **B** (send) or **C** (drop) until `confirm_timeout_s`. Rules: transient states always settle
back to idle; presses during `LISTENING`/`PROCESSING` or while the speaker is talking are ignored, and
presses queued before an attempt ended are discarded; the microphone is flushed after Sonara speaks so
it never hears itself. The controller publishes `room_state.display = {view, intent, event_id, actions}`
and the browser only renders it. Full event table: [roles/device/FLOW.md](roles/device/FLOW.md).

### Requests and honesty rules
`QUEUED → DISPLAYED → ACKNOWLEDGED → COMPLETED`, plus `NOT_DISPLAYED` and `CANCELLED`
(legal transitions in `sonara/store.py`, every change logged to an events table).
- `DISPLAYED` only after the caregiver page sends a receipt for that request, sent only when it is
  actually on screen. No receipt within `display_timeout_s` → `NOT_DISPLAYED`, shown to the patient as
  "Unable to notify your nurse" with the nurse-call fallback. Never "help is coming".
- `ACKNOWLEDGED` and `COMPLETED` only from an authenticated caregiver click.
- Only `{request_id, bed_id, intent, status, timestamps}` leaves the device, over the local network.

### Buttons and LEDs
Modulino Buttons: **A** Talk, **B** Confirm, **C** Cancel. The sketch sends a press edge with
`Bridge.notify("button", name)` and accepts `set_leds(talk, confirm, cancel)` with 0 off, 1 on, 2 blink.
Talk lights while listening; Confirm blinks while a phrase waits; Cancel lights while a sent request can
still be cancelled and blinks fast when it was not displayed. Python side: `sonara/hw/mcu.py`.

### HTTP and WebSocket API
Summary. Full contract, voice-setup routes and Web Push: [roles/device/CONTRACT.md](roles/device/CONTRACT.md).

| Route | Purpose |
|---|---|
| `GET /room`, `/caregiver`, `/static/*` | the two web apps and shared assets |
| `GET /api/health` | `{ok, state, recognizer_ready, ...}` |
| `GET /api/requests?active=true` | requests as JSON |
| `POST /api/requests/{id}/acknowledge`, `/complete` | caregiver actions, header `X-Sonara-Token` |
| `POST /api/room/input` | `{action: talk\|confirm\|cancel\|select, intent?}`, same as the buttons |
| `GET /api/metrics` | per-stage latency |
| `/api/profiles`, `/api/enrollment/*` | voice setup |
| `WS /ws?role=room` | `room_state` messages (state, pending phrase, `display`) |
| `WS /ws?role=caregiver&token=...` | `snapshot` and `request` updates; the client sends `receipt` |

### Tests and tooling
`pytest -q` runs per-role suites (`tests/test_device*`, `tests/test_speech*`); on Windows the two
speech files that import `resource` are skipped. The team coordinates on a GitHub-issue message board
(`python tools/board.py`) with a pre-commit hook for file ownership: [AGENTS.md](AGENTS.md),
[tools/README.md](tools/README.md).

### Document map
| Topic | Where |
|---|---|
| Design decisions, honesty rules | [docs/DESIGN.md](docs/DESIGN.md), [docs/PDR_v1.0.md](docs/PDR_v1.0.md) |
| Datasets, energy (SCI) | [docs/DATASETS.md](docs/DATASETS.md), [docs/SCI.md](docs/SCI.md) |
| Device: bring-up, flow, contract, phone alerts | [roles/device/](roles/device/) |
| Speech: contract, evaluation, personal candidate | [roles/speech/](roles/speech/) |
| UI: branding, rules, contract | [roles/ui/](roles/ui/) |

## Evaluation
```bash
python scripts/evaluate.py data/recordings/alice --enroll-counts 3 5 --simulated
python scripts/benchmark.py --wav data/recordings/alice/test/WATER/<file>.wav
```
`evaluate.py` expects `enrollment/INTENT/*.wav`, `test/INTENT/*.wav` and `test/_UNKNOWN/*.wav` (other
speech, coughs, noise) to measure false accepts; label acted recordings `--simulated`. Results and
limits: [roles/speech/docs/](roles/speech/docs/) · data: [docs/DATASETS.md](docs/DATASETS.md).

## Tests
```bash
pytest -q
```

## Team
Three agents and two humans work from one repo and one message board; each role writes only its
own files ([AGENTS.md](AGENTS.md)).

| Role | Owns |
|---|---|
| speech | `sonara/models`, `sonara/audio`, `sonara/recognizer.py`, `sonara/tts.py`, enrollment and evaluation |
| device | `sonara/controller.py`, `store.py`, `server/`, `hw/`, `mcu/`: state machine, requests, hardware, board bring-up |
| ui | `web/`, `assets/`, `config/intents.toml`, this README: screens, phrase texts, branding |
| lead | `docs/`, `tools/`, `roles/`, project config |

## Model provenance
- TTS voice: Piper `en_US-lessac-medium` (rhasspy/piper-voices; check its model card for license)
- Recognition uses no pretrained speech model (MFCC + DTW). The original plan, a frozen Google speech
  embedding as exported by openWakeWord v0.5.1 (Apache-2.0), was replaced; see [docs/DESIGN.md](docs/DESIGN.md).
- Font: Inter (OFL), bundled in `web/shared/fonts/`

## Privacy and safety
- Enrollment stores features only. WAVs are kept only with `--keep-audio`, locally, for consented evaluation.
- Only `{request_id, bed_id, intent, status, timestamps}` crosses the LAN. Optional Web Push
  carries a fixed generic text, never patient, bed or request data.
- `DISPLAYED` requires a caregiver-screen receipt. `ACKNOWLEDGED` requires a caregiver click.
  No receipt → the patient is told the request has **not** reached anyone.
- A phrase waiting for confirmation that times out is dropped, never sent.
- Reset: `POST /api/reset` (token) deletes request history. Delete `data/profiles/` to remove templates.

## License
MIT
