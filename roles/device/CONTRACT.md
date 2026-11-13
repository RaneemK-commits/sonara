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

Request: `{request_id, bed_id, intent, label, status, created_at, updated_at}`.
Status: `QUEUED → DISPLAYED → ACKNOWLEDGED → COMPLETED`, plus `NOT_DISPLAYED`, `CANCELLED`.

## WebSocket `/ws?role=room` | `/ws?role=caregiver&token=…`
Server → client:
- `{type: "room_state", bed_id, state: IDLE|LISTENING|PROCESSING|AWAIT_CONFIRM, pending, last: {text, intent, score, understood}, request, has_mic, intents: [{id, label}]}` (room)
- `{type: "snapshot", active: [Request], history: [Request]}` (caregiver, on connect)
- `{type: "request", request: Request}` (everyone, on every change)

Client → server (caregiver only):
- `{type: "receipt", request_id}`: send **only when the request is actually rendered on a visible screen**. This is what sets `DISPLAYED`.
