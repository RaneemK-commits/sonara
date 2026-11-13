# Sonara — Design v1.1 (changes from PDR v1.0)

The original PDR is kept in [PDR_v1.0.md](PDR_v1.0.md). This file records what changed and why.

## One-line pitch
A bedside **personal speech translator**: the patient speaks in their own way, Sonara recognises
the phrase on-device and speaks it out loud in clear English — and, if the caregiver is not in
the room, sends them the request and tells the patient honestly whether it was seen.

## Decisions (hackathon day, 2026-11-13)

| Topic | Decision | Why |
|---|---|---|
| Board | Arduino UNO Q **4GB** (Linux MPU + STM32 MCU) | Classic UNO cannot run a speech model |
| Main speech model | **Frozen pretrained speech-embedding network + few-shot per-patient prototypes** | A real neural speech model, personalised with 3–5 examples per phrase, no training run needed |
| Embedding network | openWakeWord's melspectrogram + Google speech-embedding ONNX models (~1–2 MB, 96-d embeddings every 80 ms) | Tiny, runs on Cortex-A53 CPU, trained on large speech corpora so it generalises to unseen sounds |
| Matching | DTW over embedding sequences (default) or cosine over mean-pooled embeddings | DTW keeps temporal structure of multi-syllable phrases |
| Baselines | (a) classical MFCC + DTW, (b) standard ASR (Whisper-tiny via faster-whisper) + keyword match | The three-way comparison is the technical story: standard ASR fails on atypical speech, personalised neural embeddings succeed |
| Rejection | Distance threshold (auto-calibrated from enrollment, leave-one-out) **and** margin between best and 2nd-best intent | Graceful uncertainty: ask to repeat instead of guessing |
| Output speech | Piper TTS (English, `en_US-lessac-medium`), **all prompts pre-synthesised to WAV** | Every output sentence is fixed, so live synthesis only adds latency/thermal risk; still 100% offline neural TTS |
| Language | Input: any language/dialect/vocalisation (templates are personal). Output: English | Language-agnostic input is an impact point |
| Interaction flow | Phrase is **spoken aloud immediately** in the room; **remote caregiver notification requires confirmation** (button, room screen, or voice "yes") | Fast for in-room communication, safe for remote dispatch |
| UIs | **Room display** (external screen on UNO Q, kiosk browser on `localhost/room`) + **Caregiver dashboard** (phone/laptop browser on LAN, `/caregiver`) | Organisers supplied an external display |
| Status model | `QUEUED → DISPLAYED → ACKNOWLEDGED → COMPLETED`, plus `CANCELLED`, `NOT_DISPLAYED` | Simplified from 9 states; honesty rules kept |
| Energy | VAD gates the model (model runs only on speech), pre-synthesised TTS, energy/interaction reported from a USB power meter (or labelled estimate) | Environmental judging criterion |

## Modulino (challenge requirement)
Available: Knob, Buttons, Distance, Movement.

### Core: Modulino Buttons → Talk / Confirm / Cancel
- Replaces the hand-wired buttons and LEDs (D2–D7) in `mcu/sonara_mcu/sonara_mcu.ino`. One cable to the Qwiic (I2C) connector.
- Each button's own LED gives feedback right at the patient's hand:
  - Talk: on while listening
  - Confirm: blinking while a phrase waits to be sent
  - Cancel: on while a sent request can still be cancelled
- Can be clipped to the bed rail or held, which suits limited hand use.
- The buttons call the same `on_button("talk" | "confirm" | "cancel")` interface, so the controller is unchanged.

### Stretch: Modulino Distance (time-of-flight, ~1 m range)
- **Caregiver nearby:** someone at the bedside → speak the phrase aloud only and skip "Send to
  caregiver?". Nobody nearby → offer to notify. Wording: "caregiver *nearby*", not "in the room"
  (it only sees the bedside).
- **Hands-free Talk:** the patient raises a hand over the sensor to start listening, for people who can't press a button.
- **Energy (SCI):** dim the room display and keep the model idle until someone is near; report it as a measured SCI comparison.
- Needs false-trigger handling: a person must be present for N ms before it counts.

### Not used
- Knob: volume control is nice-to-have only.
- Movement: knock-to-talk would false-trigger when the patient moves in bed.

### Check on the board first
Which side reads the Modulinos on the UNO Q, the MCU sketch (Arduino_Modulino library) or the Linux side
(App Lab)? This decides whether `mcu/sonara_mcu.ino` or `sonara/hw/mcu.py` gets the change.

## Honesty rules (unchanged, non-negotiable)
- `DISPLAYED` only after the caregiver browser sends an explicit receipt for that request ID.
- `ACKNOWLEDGED` only after an explicit caregiver click.
- If no caregiver screen receipt within the timeout → `NOT_DISPLAYED`, and the patient is told
  the request **has not reached a caregiver yet**. Never claim help is coming.
- No raw audio leaves the board. Enrollment stores embeddings/features only; WAVs are kept only
  with explicit `--keep-audio` for local evaluation.
- No urgency inferred from voice; `PAIN` is a phrase, not an assessment.

## Intents (MVP)
`HELP`, `WATER`, `FOOD`, `PAIN`, `BATHROOM` (+ control words `YES`, `NO`). Defined in
[`config/intents.toml`](../config/intents.toml) — adding a phrase needs only new enrollment takes.

## Pipeline
```
mic (USB) ─► ring buffer ─► energy VAD ─► utterance (≤5 s)
   ─► log-mel ─► speech-embedding CNN (ONNX) ─► (T × 96) sequence
   ─► DTW vs patient prototypes ─► best intent + distance + margin
   ─► accept/reject ─► play pre-synthesised WAV ("I would like some water, please.")
   ─► [confirm] ─► SQLite request ─► WebSocket ─► caregiver dashboard
                                 ◄─ receipt / acknowledge / complete
   ─► room display + spoken status
MCU (Zephyr/Arduino): Modulino Buttons (Talk/Confirm/Cancel + per-button LEDs) via Arduino Bridge RPC
                      [stretch] Modulino Distance: caregiver-nearby / hands-free talk / energy gating
```

## Resolved questions
1. Request metadata over local Wi-Fi: **allowed** by the organisers.
2. Power meter: **none**. Energy is *calculated* and labelled as such. Environmental impact is
   reported with the Green Software Foundation **SCI** standard → [SCI.md](SCI.md).
3. External display: **touchscreen**. The room UI is touch-first, and the phrase tiles double as a manual fallback.
4. Data: **TORGO** (real dysarthric speakers) for evaluation, plus our own consented recordings
   (labelled simulated) for the demo phrases → [DATASETS.md](DATASETS.md).

## Open questions
- Hackathon location (country/region), needed for grid carbon intensity *I* in SCI.
- UI design and branding: not decided.
