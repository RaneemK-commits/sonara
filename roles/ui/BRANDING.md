# Sonara branding (as shipped)

The design system that is actually live in `web/`, as of 2026-11-13 (main `021bb22`).
It starts from the humans' *Branding Guidelines v2* (light clinical, round bot) and records
every place we deliberately left it. Where this file and the v2 guidelines disagree, this file
describes what ships; where either disagrees with the honesty rules in `AGENTS.md`, honesty wins.

**In one sentence:** a calm, light, clinical bedside screen with one warm companion, the
Sonara orb, and a plain nurse list that a busy nurse can read in two seconds.

---

## 1. Design philosophy

1. **One message per screen.** The patient screen always says one thing, large, centred:
   what Sonara is doing right now. No menus, no lists, no settings.
2. **The orb is the state.** A single character carries the state on every patient screen
   (ready, listening, thinking, confirming, success, error). It replaces separate mic,
   waveform and badge graphics, so the eye never has to look for status.
3. **Honest before reassuring.** The screen never claims more than the system knows.
   "Your nurse has been notified." appears only after the nurse's phone has actually shown
   the request. We dropped v2's "They'll be with you soon." because nobody has promised that.
   Failure and disconnection are their own persistent screens, with the nurse-call fallback.
4. **Status is never colour alone.** Every state is a word plus a shape or icon. Colour
   reinforces, it does not inform on its own.
5. **Calm motion that means something.** Animation shows state (breathing, listening,
   thinking), never decoration. Every animation has a reduced-motion fallback.
6. **Patient warm, nurse plain.** Same type, neutrals and accent language, but the nurse app
   drops the character and decoration and is built for scanning.
7. **Made, not generated.** Checked against the Hallmark floor (`sloplint`) and the
   anti-slop rules in `DESIGN_RULES.md`: no emoji icons, no glass, no gradient buttons,
   no tracked caps, no invented data.
8. **Offline and light.** Plain HTML/CSS/JS, no build, no CDN, fonts bundled. The board
   (UNO Q, 1024 x 600 kiosk) must stay responsive: heavy effects belong in the presentation
   piece, not the product.

---

## 2. Logo

- **Soundmark + wordmark:** five rounded vertical bars (lengths 10, 20, 32, 22, 12, 8 units
  apart) to the left of **Sonara** in Inter ExtraLight (200, `--w-logo`), untracked, near-black `--ink`.
  The mark keeps its 2.6 stroke; the thin wordmark beside it is the brand's signature.
- Symbol: `#i-mark` (viewBox `0 0 42 40`, stroke 2.6, round caps), used inline from SVG.
- **Where it appears:** nurse app header (top left). The patient screen does **not** show the
  logo: its header is only the connection glyph, so the screen stays about the patient's need.
- Never a gradient, glow or shadow on the mark.

---

## 3. Colour

All colours are tokens in `web/shared/base.css`. No literal colours below the token block
(the orb's per-state colours are set as `--orb-*` on the room page).

### Neutrals (60 / 30)
| Token | Hex | Use |
|---|---|---|
| `--canvas` | `#FBF7F3` | page background (warm off-white) |
| `--surface` | `#FFFFFF` | cards, secondary buttons |
| `--ink` | `#161616` | text, icons, primary buttons |
| `--ink-2` | `#5E5955` | secondary text |
| `--line` | `#CFC9C2` | control borders |
| `--divider` | `#ECE7E0` | card borders, rules |
| `--on-ink` | `#FBF7F3` | text on ink buttons (never pure white) |

### State washes (patient screen floor) and accents
| State | Wash | Accent |
|---|---|---|
| Ready / thinking / sending | `--sand-wash #FBEBD6` | orb orange `#F0A868` |
| Listening | `--lavender-wash #EFE3FF` | `--violet #9B6BE6` |
| Confirm | `--lilac-wash #ECDDF8` | `--lilac #CFAEEF` (card divider) |
| Notified / acknowledged | `--green-wash #E6F2D9` | `--green #6FC043`, text `--green-ink #2F6B12` |
| Failed / offline | `--rose-wash #F8E1E4` | orb `#E0697B`, text `--rose-ink #9B2C3D` |

### Nurse accent (10)
One accent only: the orb's orange marks **what is new**.
`--orange-wash #FDEBD9` (badge), `--orange-line #F3C9A0` (new card border),
`--orange-ink #8A4A12` (badge text). Acknowledged uses the green pair. Everything else is neutral.

**Deviation from v2:** v2 asked for one accent per screen and no purple-to-blue gradients; we
keep both, and purple appears only as the listening/confirm state colour on the patient screen.

---

## 4. Typography

- **Inter** (variable, 100 to 900), bundled at `web/shared/fonts/Inter.ttf` (OFL). Fallback
  `Segoe UI, system-ui`. Features `cv11`, `ss01`.
- **Thin display type** (2026-11-14): the wordmark is ExtraLight (`--w-logo: 200`); display text
  (patient headline, confirm phrase, nurse page and section titles) is Light (`--w-display: 300`).
  Working text (bed IDs, needs, badges, buttons) keeps its weight so it stays scannable.
- Slides: `roles/ui/presentation/Sonara-template.pptx`, titles Inter ExtraLight, body Inter Light.
- Sentence case everywhere. No all-caps labels, no tracked caps.
- Tabular numerals (`.tnum`) for bed IDs and wait times.

| Patient screen (mock px, scaled) | Size | Weight |
|---|---|---|
| Headline | 48 | 300, tracking -0.015em |
| Subline / prompts | 24 | 400, `--ink-2` |
| Confirm phrase | 50 (shrinks to fit the card) | 300 |
| Buttons | 22 | 600 |

| Nurse app (px) | Size | Weight |
|---|---|---|
| Page title | 28 | 300 |
| Bed / card title | 21 | 700 |
| Request (need) | 17 | 500 |
| Meta, waits | 15 | 400 |
| Badges | 13 | 600 |
| Body minimum | 16 | |

---

## 5. Layout, space, shape

### Patient screen (`web/room`)
- **Full-bleed** on the board's 1024 x 600 display, no frame.
- Laid out in the v2 mockup's own coordinates: a 690 x 478 content box centred on screen,
  `--px: min(100vw / 690, 100vh / 478)`. Every state uses the same positions, so nothing
  reflows between states.
- **Header:** only the connection glyph, top right (black wifi; rose wifi with a cross when
  disconnected; the word is for screen readers).
- **Orb** centred at y 165; **headline + subline** stacked from y 262; long headlines wrap
  (balanced) without hitting the subline.
- **Floor:** a soft V-shaped wash of the state colour across the bottom (at least 20 % of the
  height), fading up into the canvas.

### Nurse app (`web/caregiver`)
- Single column, max 640 px, 16 px gutters, sticky header, safe-area padding for phones.
- Spacing on a 4 / 8 px scale (tokens `--space-1` to `--space-8`).
- Tap targets at least 44 px.

### Shape
- Radii: cards `8px`, chips `10px`, controls `4px`. Sharper than v2's 16 to 18 px, matching the
  mockup.
- Borders light (`--divider`), no shadows, no glass, no cards inside cards.

---

## 6. The Sonara orb (patient companion)

`<sonara-orb mode="…">` in `web/shared/orb.js`: one SVG, drawn every frame, reusable.

- **Form:** a solid round body in the state colour with two white, slanted pill eyes looking
  up and to the right. It breathes (about 1.5 %), blinks, glances around and follows a pointer
  or focused button.
- **Modes:**
  - `idle`: orange, breathing, looking around.
  - `listening`: turns violet and the circle morphs into a speech-wave ribbon (driven by mic
    level when available).
  - `thinking`: shrinks into the middle of three pulsing dots.
  - `card`: stretches into the lilac confirm card; the phrase fades in on top of it.
  - `success`: green, happy (arched) eyes.
  - `error`: rose, eyes half-closed.
  - `speaking`: mouth animation (reserved until the device reports real playback).
- Reduced motion: the same states at a quarter of the speed, no large movement.

**Deviation from v2:** v2 suggested a cream body with dark eyes and a glow halo. We use a
solid state-coloured body with white eyes and no glow (glowing orbs read as generic AI).

---

## 7. Patient screens and copy

The device decides the view (`room_state.display.view`); the page only renders it. Offline is
the only state the page decides itself (the socket is gone).

| View | Orb | Headline | Subline |
|---|---|---|---|
| ready | idle | What do you need? | Just speak, and I’ll let your nurse know. |
| listening | listening | I’m listening… | Tell me what you need. |
| processing | thinking | One moment… | Working out what you said. |
| confirm | card | Did you mean… / **I need water?** | Press B to send it, or C if it’s wrong. |
| retry | idle | I didn’t understand. | Please try again. |
| cancelled | idle | Okay, not sent. | Say something whenever you’re ready. |
| request_cancelled | idle, grey | **Water request cancelled.** (a request already sent was withdrawn) | If you still need something, just ask again. |
| yes | success (green) | **Yes** (110 px) | |
| no | idle, rose | **No** (110 px) | |
| sending | thinking | Sending to your nurse… | |
| notified | success | Your nurse has been notified. | |
| acked | success | Your nurse acknowledged your request. | |
| failed | error | Unable to notify your nurse. | Use the existing nurse-call system. |
| offline | error | Not connected. | Use the existing nurse-call system. |

- **Confirm phrases:** WATER "I need water?", HELP "I need help?", FOOD "I’m hungry?",
  PAIN "I’m in pain?", BATHROOM "I need the bathroom?", with a line icon left of a divider.
- **Confirm buttons** (the board has a touchscreen), in the Modulino's physical order with keycaps:
  A Say it again, **B Yes, send** (ink), C No, don’t send.
- **A/B/C legend** under the text on every other view: A Talk, B Confirm, C Cancel (C reads
  "Cancel request" while a sent request is open). Shown only when the device sends
  `display.actions`; a button that does nothing right now is greyed (32% opacity), never hidden.
- **Yes / No** answer the room: a spoken yes or no with nothing pending, set large enough to
  read from across the room. The page never claims it was spoken aloud.
- **"Playing aloud…" pill:** hidden whenever the device sends `display`, because no real
  playback events exist yet. We never claim speech is playing when it is only queued.
- Copy rules: short, gentle, sentence case, no jargon, no promises the system cannot keep.

---

## 8. Nurse app

Plain and fast. No character, no decoration.

- **Header:** logo left; right side is two bare black icons: connection (wifi, or wifi with a
  cross) and the **alert bell** (crossed out when off). The bell is a real on/off toggle, plays
  a test beep when turned on and remembers the choice.
- **All patients (`/caregiver`):** title "Requests", count "N active, N new". One card per
  active request, oldest new first, acknowledged after: bed (with an arrow), wait time, need,
  status badge (bell + "New" in orange, or tick + "Acknowledged" in green) and one action
  (**Acknowledge** filled ink, **Resolve** outlined). Beds with nothing active show
  "No active request".
- **Grouping:** when one bed asks again within 5 minutes of its previous request, the requests
  share one card: needs summed up ("Water ×2, Pain"), wait from the first, badge "3 new" (or
  "1 new of 3"), and one action for the group: **Acknowledge all** (the new ones), then
  **Resolve all**. The patient page still lists them one by one.
- **Patient page (`/caregiver#bed=<id>`):** tap a patient card. "All patients" back link, bed
  as the title, "N active, N earlier", the patient's active requests (need and time first) with
  their actions, then **Earlier requests** newest first: need, date and time, and
  "Resolved" (tick) or "Cancelled by patient" (cross).
- **Never hide a new request:** on a patient page, other patients' new requests stay visible
  in an orange strip at the top ("New from BED-02: Water").
- **Disconnected:** a rose banner in words under the title, in addition to the icon.
- Rows never reorder under a nurse's finger.

---

## 9. Iconography

- One line family, 24 px grid, stroke 2 to 2.6, round caps and joins, `currentColor`.
- Inline SVG `<symbol>`s per page; no emoji, no icon fonts, no CDN.
- Set in use: soundmark, wifi, wifi-off, bell, bell-off, mic, check, x, retry, speaker,
  clock, alert, chevrons, and one icon per intent (water glass, fork and spoon, toilet,
  heart, bell for help).

---

## 10. Motion

- `transform` and `opacity` only on HTML; the orb animates its own SVG geometry.
- View changes fade in over 0.25 s; the orb eases between modes (no hard cuts).
- Nurse cards: a new request settles in once (fade + 4 px drop).
- Everything respects `prefers-reduced-motion`.

---

## 11. Start-up animation (presentation only)

`<sonara-intro>` in `web/shared/intro.js`, preview at `/static/intro/` (Replay button,
`?size=` for the logo size).

The lockup slides in from the left and stops in the middle; the wordmark wipes back into the
soundmark; the bars swell and melt together into a black blob; orange spreads out from its
centre; the circle wakes up as the orb (eyes open, small squash) and can fly onto a target.

**Not on the board.** It cost about 1.4 CPU cores on the UNO Q, so it was removed from the
room display (`cfa704e`) and is kept for the pitch and videos only.

---

## 12. Accessibility

- High contrast text; patient headline readable from the bed.
- Status as word + icon; connection word available to screen readers.
- Focus ring: 3 px ink outline, offset 3 px, instant.
- 44 px minimum touch targets on the phone.
- Reduced motion honoured everywhere.

---

## 13. Deviations from Branding Guidelines v2 (summary)

| v2 says | We ship | Why |
|---|---|---|
| "They’ll be with you soon." | dropped | honesty rule: nobody has promised it |
| Logo top-left on the patient screen | no logo on the patient screen | the screen is about the patient's need |
| Green "Connected" chip with a word | bare wifi glyph (word for screen readers) | quieter; user decision |
| Cream bot, dark eyes, glow | solid state-coloured orb, white eyes, no glow | warmer, less generic |
| Large mic + bot on home | the orb is the only focal point | one character carries every state |
| Radii 16 to 24 px, dark screen frame | 4 / 8 / 10 px, full-bleed | matches the mockup and the 1024 x 600 board |
| Nurse: ward name, filter chips, priority | count, per-patient pages, New / Acknowledged | no ward or priority data exists; never invent data |
| Read-aloud pill always on confirm | hidden until real playback events exist | do not claim speech that is only queued |
