# Live end-to-end test — 2026-11-13

Scope: live UNO Q, MCU buttons, speaker, room display, friend's Android/Chrome caregiver
dashboard on local HTTP. Optional Web Push/HTTPS disabled at the human's request.
Recognition acceptance below is **simulated** via POST /api/room/input select WATER;
it is not a speech accuracy result. All event times below are UTC from the server log.

| Check | Observed result |
|---|---|
| Real A + spoken WATER | Rejected: understood=false, score=0; no request created. Existing profile requires more enrollment. Voice path not passed. |
| Simulated WATER before B | AWAIT_CONFIRM, display=confirm, pending Water; active requests empty. |
| Human B confirmation | req-0005 QUEUED at 21:42:40, actor patient. |
| Phone rendering receipt | req-0005 DISPLAYED at 21:42:40, actor caregiver_screen. Room display=notified. |
| Speaker log | Water phrase, ask_send, sending, and displayed prompts logged. Audible confirmation from human still pending. |
| Phone alert sound | First req-0005 displayed, but human reported phone silent. Checking bell test/unlock and repeating; UI NEED posted. Not passed yet. |
| Acknowledge, Resolve, history | Pending. |
| Cancel before sending | Pending in this run. |
| No caregiver/reconnect | Passed earlier live run req-0004; repeat if time permits. |
| Restart/power-cut recovery | Automated SQLite reopen passed; physical test pending. |

Speech owner notified of real recognition rejection; no thresholds changed or rejection bypassed.

## Second simulated WATER attempt (after phone bell off/on instruction)

- req-0006 QUEUED and DISPLAYED at 21:45:30 UTC; confirmed via human B and actual
  caregiver-screen receipt. Room display followed confirm → sending → notified.
- ACKNOWLEDGED at 21:45:40 UTC, actor caregiver; speaker log contains acknowledgment
  prompt at the same time. Human confirmed both bell test and request alert audible,
  acknowledgment spoken, and Resolve moved the request into history.
- req-0005 from the first attempt remains separate; do not delete test history or mark
  another request completed automatically.
- Cancel-before-send attempt was not injected: automatic approval review hit its usage
  limit before executing the command. Do not claim this or physical reboot passed.
- Human requested louder phone chime after successful sound check; prepared UI handoff
  patch locally, not deployed.
