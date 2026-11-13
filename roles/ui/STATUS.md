# ui STATUS

Live backlog for the `ui` agent. Update before you stop so a fresh session can resume.

## Now
- Branch `ui/branding`: room + caregiver pages restyled to branding v2 (light clinical canvas, pastel state washes, cream Sonara bot, nurse worklist). Verified end-to-end with `--no-audio`.
- Next: phrase texts review in `config/intents.toml`, pitch.

## Published
- (commits other roles can rely on)

## Decisions
- 2026-11-13: branding = humans' Sonara handoff (dark evergreen / mint glass). Kept plain HTML, no Vue build (AGENTS: fewest files, no frameworks).
- 2026-11-13: room screen has no touch controls; demo buttons only with `?demo` or key D, labelled simulated.
- 2026-11-13: "Your nurse has been notified" only on DISPLAYED (caregiver-screen receipt); NOT_DISPLAYED shows the fallback error and is never auto-hidden.
- 2026-11-13: switched to branding v2 (light). Dropped v2's "They'll be with you soon." (AGENTS hard rule 4: never claim help is coming). Confirm screen has touch Yes/No/Try again (board has a touchscreen). No "Playing aloud…" pill: device sends no TTS events yet.
