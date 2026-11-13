# Role brief: device (RaneemK-commits)

You own what happens after recognition: the state machine, request store, server, and the
hardware on the UNO Q. Files: see the ownership table in [../../AGENTS.md](../../AGENTS.md).

## Priorities
1. UNO Q bring-up: Python env, USB mic and speaker visible to ALSA, server reachable on the LAN.
2. Modulino **Buttons** → Talk / Confirm / Cancel, with per-button LEDs. Find out which side reads them (MCU sketch or Linux) and update `mcu/` or `sonara/hw/mcu.py`.
3. Reliability: reconnect/replay, the `NOT_DISPLAYED` path, reboot recovery of open requests.
4. Stretch: Modulino **Distance**: caregiver-nearby, hands-free Talk, display/model gating for SCI.

## Never
- Dispatch a request without patient confirmation, or mark `ACKNOWLEDGED` without a caregiver click.
- Change the HTTP/WebSocket API in `CONTRACT.md` without a `CONTRACT` post to `ui`.
