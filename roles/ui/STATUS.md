# ui STATUS

Live backlog for the `ui` agent. Update before you stop so a fresh session can resume.

## Now
- main `021bb22`, deployed to the board. Design system written down in `roles/ui/BRANDING.md`.
- Room renders the device-owned `room_state.display` (fallback kept); not yet validated against
  `codex/device-room-state` because it is not on main.
- Open: voice-setup (enrollment) screen. Speech's `roles/speech/integration/ui.patch` targets the
  pre-v2 room page, so it has to be rebuilt on the current design against `/api/profiles` and
  `/api/enrollment/*` (`roles/device/CONTRACT.md`).
- Open: `config/intents.toml` says "caregiver" where the screens say "nurse" (speech regenerates audio).

## Published
- `82851b5`: room renders `display.view` / `display.intent` / `event_id` (device room-display.patch).
- `021bb22`: nurse app per-patient pages (`/caregiver#bed=<id>`); receipts only for rendered requests.
- `web/shared/orb.js` (`<sonara-orb>`), `web/shared/intro.js` (`<sonara-intro>`, presentation only).

## Decisions
- 2026-11-13: branding = humans' Sonara handoff (dark evergreen / mint glass). Kept plain HTML, no Vue build (AGENTS: fewest files, no frameworks).
- 2026-11-13: room screen has no touch controls; demo buttons only with `?demo` or key D, labelled simulated.
- 2026-11-13: "Your nurse has been notified" only on DISPLAYED (caregiver-screen receipt); NOT_DISPLAYED shows the fallback error and is never auto-hidden.
- 2026-11-13: switched to branding v2 (light). Dropped v2's "They'll be with you soon." (AGENTS hard rule 4: never claim help is coming). Confirm screen has touch Yes/No/Try again (board has a touchscreen). No "Playing aloud…" pill: device sends no TTS events yet.
- 2026-11-13: UI restarted under roles/ui/DESIGN_RULES.md (Hallmark floor, 60-30-10, 8pt). Atkinson Hyperlegible bundled (OFL, web/shared/fonts). Palette from the v2 mockup minus purple; green = delivered/acknowledged state only, primary buttons ink. Flat line-drawn face replaces the orb. sloplint --scope app: clean.
- 2026-11-13: user rejected the rules-based rebuild; room display now built to v2 mockup coordinates (Inter bundled, no character). Dropped "They'll be with you soon." (hard rule 4). "Playing aloud…" pill shows for 4 s on confirm (shortcut until device sends TTS events).
- 2026-11-13: human added the Sonara orb (`orb.js`) as the one patient-screen character (idle, listening wave, thinking dots, morphs into the confirm card, success, error); room header is only the wifi glyph, no logo.
- 2026-11-13: start-up intro (logo slides in, bars melt into the orb) built as `<sonara-intro>`; removed from the room display after it cost ~1.4 CPU cores on the board, kept at /static/intro/ for the pitch.
- 2026-11-13: nurse app passes sloplint; one accent (orb orange = new), bare black wifi and bell icons, bell is a real toggle.
- 2026-11-13: nurse history moved from a list to per-patient pages (tap a patient); other beds' new requests stay visible on a patient page so receipts stay honest.
- 2026-11-13: design system and every deviation from the v2 guidelines recorded in `roles/ui/BRANDING.md`.
