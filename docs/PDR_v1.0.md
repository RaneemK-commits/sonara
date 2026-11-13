# Sonara — Product Design Requirements

**Version:** 1.0 | **Status:** Hackathon MVP | **Platform:** Arduino UNO Q | **Team:** 4 | **Duration:** 24 hours

## 1. Executive summary
Sonara is an offline-first bedside communication prototype for patients who have difficulty producing intelligible speech. A patient produces a practiced vocalization or fragmented phrase; the device processes audio locally, recognizes a predefined intent, reads it back using offline text-to-speech (TTS), and—with confirmation—sends a structured request to a caregiver dashboard on the same local network. The caregiver acknowledges or completes the request; the device speaks the resulting status to the patient.

**Tagline:** Giving every voice a way through.

**Value proposition:** Close the communication loop, not just recognize a voice command.

**Architecture decision:** No agent, no LLM, no cloud. All processing, inference, TTS, server, persistence and dashboard assets execute on the Arduino UNO Q. A caregiver phone or laptop is only a local browser client.

**Safety:** Prototype only; not a certified medical device, emergency call system, or replacement for conventional nurse-call hardware. No real patients or real clinical deployment in the hackathon.

## 2. Problem and users
**Primary user:** A patient with limited or atypical speech who can produce some repeatable vocalizations but may be unable to use a phone or touchscreen.

**Secondary user:** A caregiver monitoring requests from one or more beds on a browser dashboard.

**Problem:** Ordinary speech recognition may fail on nonstandard speech, while a recognized request alone does not guarantee that anyone receives or acknowledges it.

## 3. Product principles
1. **Patient-controlled:** Confirmation before dispatch; explicit cancel; avoid inventing medical meaning.
2. **Local-first:** All raw audio, audio features, enrollment samples, speech recognition and TTS stay on the UNO Q. The dashboard receives only structured request metadata.
3. **Graceful uncertainty:** Low-confidence recognition triggers repeat or manual fallback, never a fabricated interpretation.
4. **Closed-loop:** Created → Delivered → Acknowledged → Completed, with distinct UI and spoken feedback.
5. **Energy-aware:** The MCU manages low-cost input and controls; the Linux MPU performs heavier inference on demand.
6. **Open-source:** Publish source, model provenance, setup steps, and reproducible benchmarks.

## 4. MVP user journey
1. Caregiver configures bed ID and enrolls 5–8 predefined requests using a few examples each.
2. Patient presses a large talk button (or an optional wake trigger), speaks a short phrase or practiced vocalization.
3. The device captures audio, applies VAD, filtering and feature extraction, and ranks enrolled intents.
4. If confidence is insufficient, it says: “I didn't understand. Please try again.”
5. If recognized, it says: “I heard: water, please. Press confirm to send, or cancel.”
6. Patient confirms; the device queues and transmits `{request_id, bed_id, intent, created_at}` over local Wi-Fi.
7. Dashboard shows an incoming request and emits a local visual/audio alert. It sends an acknowledgment of receipt.
8. Caregiver chooses “Acknowledge” and later “Complete.”
9. Device receives each status and speaks: “Your request was received” / “A caregiver has acknowledged your request.”
10. If delivery or caregiver acknowledgment does not occur, device clearly says the request has **not** been acknowledged and shows an alert indicator. Do not claim assistance is coming.

## 5. Functional requirements
| ID | Priority | Requirement | Acceptance criterion |
|---|---|---|---|
| FR-01 | Must | Capture speech with local microphone | A 1–5 second utterance is captured reliably |
| FR-02 | Must | Process speech locally | Demonstrate audio stays on the board with internet disconnected |
| FR-03 | Must | Recognize 5 predefined intents | Held-out trial results reported, including errors |
| FR-04 | Must | Offline speech synthesis | Spoken confirmation and status messages work with no internet |
| FR-05 | Must | Confirm/cancel before dispatch | No request is sent after cancellation |
| FR-06 | Must | Caregiver dashboard | New request appears with bed, intent, time, status |
| FR-07 | Must | Local notification | New request creates a visible alert and optional browser sound |
| FR-08 | Must | Two-way status updates | Acknowledge/complete changes dashboard and patient device |
| FR-09 | Must | Delivery failure handling | Offline or unreachable dashboard never appears as delivered |
| FR-10 | Must | Basic event history | Structured metadata history visible; no stored raw audio |
| FR-11 | Should | Personalized enrollment | Add examples for a phrase without retraining a large model |
| FR-12 | Should | Energy and latency metrics | Report per-stage latency and measured or clearly labeled estimated power |
| FR-13 | Could | Multi-bed support | Dashboard distinguishes multiple simulated beds |
| FR-14 | Could | Voice-only confirmation | Restricted confirmation vocabulary with conservative thresholds |

## 6. Example intents
`WATER`, `REPOSITION`, `BLANKET`, `RESTROOM_ASSISTANCE`, `DISCOMFORT`, `GENERAL_HELP`, `CANCEL`, `REPEAT`.

These are requests, not medical assessments. Do not assign urgency from acoustic emotion, infer diagnoses, or trigger treatment. A separate conventional emergency mechanism remains required.

## 7. Technical architecture
```text
[Microphone] → [UNO Q / Debian Linux]
                  VAD + DSP → MFCC/log-mel features
                  → personalized DTW/template classifier
                  → intent + confidence → local Piper TTS
                                      ↓
                         [Confirmation state machine]
                                      ↓
                       [Local event queue / SQLite]
                                      ↓
                      [HTTP/WebSocket server on UNO Q]
                                      ⇅ local Wi-Fi only
                      [Caregiver browser dashboard]
                                      ↓
                       acknowledge / complete events
                                      ↓
                          [Patient feedback via TTS]

[STM32 MCU / Zephyr] → buttons, LEDs, watchdog, sensor events
                           ⇅ Arduino inter-processor messaging
[Linux MPU] → audio pipeline, classifier, TTS, local server
```

**Deployment boundary:** A local Wi-Fi access point/router may provide LAN connectivity, but it must not host application logic, storage, or inference. A browser executes ordinary UI rendering and user input only; no speech models run in the browser. The UNO Q must be able to run its backend and speech pipeline with the WAN disconnected.

**Preferred networking:** UNO Q hosts a local web server on an isolated LAN; caregiver uses browser on a laptop or phone. Internet is unnecessary, but the dashboard does require local network connectivity. Do not call the whole system fully disconnected. A local browser receiving structured intent metadata does not receive raw audio. Validate whether the hackathon interprets “nothing is sent” to prohibit even metadata; if so, use a wired local display or obtain explicit clarification.

**On-board deployment:** Preinstall all model weights and Python dependencies before the demo. Run a single lightweight Linux service (or a small number of supervised processes) with bounded audio buffers; use pre-synthesized on-device fallback prompts if Piper cannot meet latency targets. Confirm memory and thermal behavior on the real board before finalizing the model.

**Speech model:** Personalized MFCC + dynamic time warping is the minimum feasible acoustic recognition baseline. Compare against an optional small offline STT model if it runs adequately. Piper provides neural speech synthesis. This is a hybrid speech-to-speech system, not a full end-to-end neural speech translation model.

## 8. Data and APIs
**Request object:**
```json
{
  "request_id": "req-0001",
  "bed_id": "BED-01",
  "intent": "WATER",
  "status": "PENDING_DELIVERY",
  "created_at": "2026-11-13T10:00:00Z",
  "updated_at": "2026-11-13T10:00:00Z"
}
```

**Status transitions:** `DRAFT → CONFIRMED → QUEUED → DISPLAYED → ACKNOWLEDGED → COMPLETED`. Alternate states: `CANCELLED`, `NOT_DISPLAYED`, `FAILED`. `QUEUED` means durably saved on the UNO Q; `DISPLAYED` requires an explicit browser receipt for the request ID (not merely successful WebSocket send). Neither status implies a human saw the request. Only an explicit caregiver action sets `ACKNOWLEDGED`. If the browser is absent, remain `QUEUED` or show `NOT_DISPLAYED` after a timeout; do not silently mark delivered. Persist idempotency keys and replay outstanding events on reconnect.

**Authentication:** Use a local caregiver login or access token for dashboard actions, avoid exposing the service to the public internet, and do not include patient-identifying details in demo events. HTTP on a trusted isolated hackathon LAN is a prototype compromise, not production security.

**Suggested endpoints:** `POST /api/requests`, `GET /api/requests`, `POST /api/requests/{id}/acknowledge`, `POST /api/requests/{id}/complete`, `GET /api/health`, and `WS /ws/events`. If the server is on the device, its internal request creation can use a local function rather than HTTP.

**Data handling:** No raw voice transmitted; enrollment samples kept only locally and deleted after feature extraction where feasible; store only consented acoustic templates and minimal event metadata. Provide clear reset/delete functionality. Use demo identities, not real patient information. On a shared network, add basic authentication and transport protection if feasible; do not describe a hackathon demo as clinically secure.

## 9. Interface requirements
**Patient hardware:** Talk, Confirm, Cancel buttons; one LED for listening, one for pending/unacknowledged, one for acknowledged; speaker for read-back and status. Use distinct patterns, not color alone.

**Caregiver dashboard:** Header with connection status; active request queue; request card with bed, intent, elapsed time, and status; Acknowledge and Complete buttons; recent history; clear error state for device disconnection. Optional browser sound must be enabled by user interaction due to autoplay restrictions.

## 10. Nonfunctional targets (aspirational, not claims)
- End-to-end recognition and spoken confirmation: target < 5 seconds after utterance ends; benchmark on actual board.
- Local dashboard update: target < 1 second after dispatch on healthy LAN.
- Zero false “acknowledged” messages without explicit caregiver action.
- Uncertain utterances should be rejected rather than automatically dispatched.
- No cloud dependency; no raw audio sent to dashboard.
- Reboot recovery for uncompleted structured requests if persistence is enabled.

## 11. Evaluation
**Recognition:** held-out accuracy per intent, confusion matrix, false acceptance, rejection rate; quiet and background-noise conditions. Use real consented recordings where available, otherwise label acted examples as simulations and do not claim patient validity.

**Speech:** intelligibility of synthesized messages, TTS latency, confirmation success.

**Workflow:** percentage of dispatched requests appearing on dashboard, notification latency, acknowledgment round-trip, network interruption/reconnection behavior, duplicate-event handling.

**Edge/sustainability:** CPU usage, idle versus inference energy, energy per completed interaction. Measure with external hardware if available; distinguish measurement from software estimates.

## 12. 24-hour execution plan
| Window | Developer 1 — Speech | Developer 2 — Backend | Developer 3 — Frontend | Developer 4 — Hardware/integration |
|---|---|---|---|---|
| 0–3h | Test audio capture + TTS | Define events/statuses | Dashboard wireframe | Bring up UNO Q, buttons, LAN |
| 3–8h | MFCC + DTW baseline | Local API + WebSocket | Request queue + alerts | MCU events + LEDs |
| 8–13h | Enrollment + confidence | Persistence + transitions | Ack/complete actions | Integrate TTS + buttons |
| 13–18h | Noise tests + tuning | Retry/error handling | Connection/error states | Full end-to-end tests |
| 18–21h | Recognition metrics | Network metrics | Demo polish | Energy/latency benchmark |
| 21–24h | Fixes | Fixes | Pitch/demo | Freeze build + rehearse |

**Fallback order:** 1) Live device → dashboard → acknowledgment → spoken status. 2) Five intents with prerecorded enrollment. 3) No enrollment UI. 4) No multi-bed. 5) No optional wake word. Do not sacrifice the closed-loop workflow for an ambitious model.

## 13. Demo script
1. Disconnect internet; show that audio inference and TTS still work.
2. Patient speaks a practiced, nonstandard phrase into microphone.
3. Device repeats the interpreted intent; patient confirms with button.
4. Caregiver dashboard receives a visible alert and shows `BED-01 / WATER`.
5. Caregiver clicks Acknowledge; patient hears an acknowledgment message.
6. Caregiver clicks Complete; request moves to history.
7. Repeat under noise; show a low-confidence rejection.
8. Disconnect the local network; show honest undelivered state and retry behavior.
9. Show recognition, latency, and energy measurements.

## 14. Risks and mitigations
| Risk | Impact | Mitigation |
|---|---|---|
| Model struggles with atypical speech | High | Personalized limited vocabulary; confidence rejection; avoid medical claims |
| TTS too slow on UNO Q | High | Benchmark immediately; pre-generate fixed prompts locally as fallback |
| Browser notifications unreliable | Medium | Persistent visible queue and connection indicator; optional audio after user interaction |
| Wi-Fi disconnect | High | Queue locally, retry, show explicit not-delivered state |
| Wrong intent dispatched | High | Read-back + confirmation; cancel; never infer emergency severity |
| Time overruns | High | Build closed-loop skeleton before improving recognition |
| Privacy leak | High | Never transmit raw audio; no third-party services; use demo data |

## 15. Definition of done
- [ ] Device captures a real spoken/vocalized input and classifies it locally.
- [ ] Device speaks a confirmation via offline TTS.
- [ ] Patient can confirm or cancel physically.
- [ ] Confirmed request reaches a local caregiver dashboard.
- [ ] Caregiver can acknowledge and complete it.
- [ ] Acknowledgment is spoken back to the patient.
- [ ] Uncertain recognition and failed delivery produce clear error states.
- [ ] No internet or cloud APIs are needed.
- [ ] Demo includes latency and recognition results; energy measurement if instrumentation permits.
- [ ] Open-source repository includes setup, limitations, license, and reproducible demo steps.

## 16. Non-agentic scope and decision logic
The system follows deterministic request-handling rules only: audio capture → recognition → patient confirmation → request persistence → dashboard notification → caregiver acknowledgment → patient feedback. Timeouts and reconnection are standard application reliability mechanisms, not autonomous agent planning. There is no independent task prioritization, caregiver selection, diagnosis, medical recommendation, or autonomous escalation.

## 17. Open decisions
1. Are USB microphone and speaker available, and what buttons/LEDs can be attached?
2. Is the caregiver dashboard allowed to receive structured intent metadata on local Wi-Fi under the organizers' privacy rules?
3. Should the first MVP support one bedside unit only?
4. Will enrollment examples come from team members (simulated) or appropriately consented representative recordings?
5. Can an external USB power meter or current sensor be used for actual energy measurement?
