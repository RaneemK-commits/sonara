# Device-owned end-to-end flow

The controller owns interaction and display transitions. SQLite owns durable request
transitions. The room renders `room_state.display`; the caregiver sends a receipt only
after visibly rendering a request, and acknowledgment only after a human click.

| Event | Interaction | Room display | Request effect |
|---|---|---|---|
| Talk | LISTENING | listening | none |
| Captured audio | PROCESSING | processing | none |
| Rejection/no usable audio | IDLE or existing AWAIT_CONFIRM | retry for 5 seconds | none |
| Accepted request phrase | AWAIT_CONFIRM | confirm with pending intent | none |
| Confirm before deadline | IDLE | sending | create QUEUED |
| Confirm after deadline | IDLE | cancelled | none |
| Cancel pending phrase / confirmation timeout | IDLE | cancelled for 5 seconds | none |
| No caregiver receipt in 10 seconds (configured) | unchanged | failed when no interaction feedback overrides it | NOT_DISPLAYED |
| Actual caregiver-screen receipt | unchanged | notified | DISPLAYED |
| Caregiver acknowledgment | unchanged | acked | ACKNOWLEDGED |
| Caregiver Resolve | unchanged | ready | COMPLETED |
| Patient cancels an unacknowledged request | unchanged | cancelled | CANCELLED |
| Transport disconnect | unchanged | browser offline override | no fabricated transition |
| Reconnect | unchanged | current authoritative snapshot | replay durable requests |

Every attempt/rejection has a process-local event ID. Identical rejection scores are
different events. Retry feedback temporarily outranks pending confirmation; its expiry
restores the actual pending intent, not the rejected result. New deliberate input clears
old feedback. Busy Talk/select presses and premature confirms cannot queue a future action.
Confirmation deadlines are checked even under input load and again at dispatch.

The existing 60-second recency of displayed/acknowledged/cancelled feedback is decided
by device time. NOT_DISPLAYED never ages into success. Store recovery is durable;
unconfirmed interactions and short-lived feedback are intentionally not recovered on reboot.

## Integration still required

- UI owner applies `integration/room-display.patch` to render the authoritative display
  and remove the guessed playback pill. Human explicitly requested leaving UI edits to UI.
- Speech owner supplies actual playback lifecycle callbacks before we can claim a
  truthful speaking/finished/error state. Queuing `say()` is not proof of playback.
- Existing room texts and styling remain UI-owned. No new patient wording is introduced.

Regression checks in `tests/test_device.py` cover repeated identical rejection,
reconnect snapshots, feedback expiry publication, pending-phrase recovery, expired
confirmation, busy inputs, honest delivery progression and on-disk request recovery.
