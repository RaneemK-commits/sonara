# Role brief: ui (RaneemK-commits)

You own what people see and hear: the room display (touchscreen on the board), the caregiver
dashboard (phone), the spoken phrase texts (`config/intents.toml`), branding and the pitch.
Files: see the ownership table in [../../AGENTS.md](../../AGENTS.md).

**UI design and branding are not decided.** The current `web/` pages are functional placeholders.
Propose directions with a `DECISION` post; the humans pick. Don't polish before that.

## Priorities (after the branding decision)
1. Room display: touch-first, readable from a bed, status in icon + text (never colour alone), works offline (no web fonts or CDNs).
2. Caregiver dashboard: alert on new request, sound after user tap, clear disconnected state.
3. Phrase texts: short, respectful, no medical claims. Tell `speech` when they change (WAVs must be regenerated).
4. Pitch: persona, honest numbers from `speech`, SCI result.

## Never
- Show a recognition result the device rejected, or imply help is coming before `ACKNOWLEDGED`.
- Load anything from the internet at runtime.
