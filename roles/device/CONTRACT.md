# device CONTRACT: the API ui builds on

Change only with a `CONTRACT` post to `ui`.

## HTTP
| Method | Path | Auth | Body / result |
|---|---|---|---|
| GET | `/room`, `/caregiver` | — | serve `web/room/index.html`, `web/caregiver/index.html`; `/static/*` serves `web/` |
| GET | `/api/health` | — | `{ok, bed_id, caregiver_screens, room_screens, state, recognizer_ready}` |
| GET | `/api/requests?active=true` | — | list of Request |
| POST | `/api/requests/{id}/acknowledge` | `X-Sonara-Token` | Request (409 if not allowed from current status) |
| POST | `/api/requests/{id}/complete` | `X-Sonara-Token` | Request (requires `ACKNOWLEDGED`) |
| POST | `/api/room/input` | — | `{action: "talk"|"confirm"|"cancel"|"select", intent?: ID}` |
| GET | `/api/metrics` | — | per-stage latency summary |
| POST | `/api/reset` | `X-Sonara-Token` | deletes request history |

### Voice setup (enrollment), added 2026-11-13 with speech
All return JSON from `EnrollmentService`; 409 = mic/profile busy, 422 = bad input/profile data, 503 = mic unavailable.
While enrollment is active, `/api/room/input` returns 409 for `talk` and `select` (confirm/cancel still work).

| Method | Path | Body / purpose |
|---|---|---|
| GET | `/api/profiles` | active profile, profile list, ready/error, counts, calibration, intents |
| POST | `/api/enrollment/start` | `{profile_id, keep_audio: false}`; pauses recognition |
| POST | `/api/enrollment/intent` | `{intent}` |
| POST | `/api/enrollment/capture` | `{manual: true, seconds: 0.3..5}`; stage one take from the device mic |
| POST | `/api/enrollment/sample` | keep the staged take (stores MFCCs, never audio unless keep_audio) |
| DELETE | `/api/enrollment/intents/{intent}` | clear all takes for an intent |
| DELETE | `/api/enrollment/intents/{intent}/samples/{index}` | delete one take |
| POST | `/api/enrollment/calibrate` | recompute thresholds |
| POST | `/api/enrollment/test` | `{manual, seconds}`; test the draft, never creates a request |
| POST | `/api/enrollment/finish` | save + load profile, resume recognition |
| POST | `/api/enrollment/cancel` | discard draft, resume recognition |
| POST | `/api/profiles/{profile_id}/load` | switch profile |
| DELETE | `/api/profiles/{profile_id}` | delete profile (and opt-in recordings) |

Request: `{request_id, bed_id, intent, label, status, created_at, updated_at}`.
Status: `QUEUED → DISPLAYED → ACKNOWLEDGED → COMPLETED`, plus `NOT_DISPLAYED`, `CANCELLED`.

## WebSocket `/ws?role=room` | `/ws?role=caregiver&token=…`
Server → client:
- `{type: "room_state", bed_id, state: IDLE|LISTENING|PROCESSING|AWAIT_CONFIRM, pending, last: {text, intent, score, understood}, request, has_mic, enrollment_active, intents: [{id, label}]}` (room). `has_mic` is false while enrollment owns the mic.
- `{type: "snapshot", active: [Request], history: [Request]}` (caregiver, on connect)
- `{type: "request", request: Request}` (everyone, on every change)

Client → server (caregiver only):
- `{type: "receipt", request_id}`: send **only when the request is actually rendered on a visible screen**. This is what sets `DISPLAYED`.

## Authoritative room display (additive)
`room_state.display = {view, intent, event_id}`. Existing `state` and request statuses remain unchanged.
`view` uses existing UI names: ready, listening, processing, confirm, retry, cancelled,
sending, failed, notified, acked. The browser renders this field directly; only transport
disconnect and explicit demo previews override it locally. Do not infer retry from identical
`last` values or expire device views using browser timers. `intent` retains the pending phrase
during rejection/retry, and `event_id` distinguishes repeated attempts/outcomes within a process.
Snapshots on reconnect include the current display; event IDs are not durable across restart.

Priority: capture/processing → five-second retry/cancel feedback → pending confirmation →
request status → ready. Feedback expiry is published by the controller. QUEUED and
NOT_DISPLAYED never expire into success. DISPLAYED/ACKNOWLEDGED/CANCELLED use the existing
60-second recency rule, now on device time. COMPLETED returns to ready.
An expired confirmation cannot create a request, including under queued input load.
This does not claim actual TTS playback: no playback start/end contract exists yet.
