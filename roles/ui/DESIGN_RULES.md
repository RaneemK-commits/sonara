# ui design rules

Binding for every change in `web/`. The design system itself (colours, type, the orb, every
screen and its copy) is in [BRANDING.md](BRANDING.md); these are the rules every change must
pass. Checked with the Hallmark linter (`node ~/.claude/skills/hallmark/scripts/sloplint.mjs
<file> --scope app`) and the anti-ui-slop finish gate before each push.

> **2026-11-13, user decision:** the v2 light mockup is the spec. Inter, the purple
> listening/confirm colours and the Sonara orb are part of the brand. The honesty rules at the
> bottom always bind.

## Banned
- Purple-to-blue gradients, gradient buttons, glow halos, floating glass cards, backdrop blur.
- Emoji as icons. Cards inside cards. Eyebrow labels or tracked all-caps labels. Decorative status dots or side stripes.
- Middle-dot or dash-joined meta strings ("3 active · 1 new"); use a comma.
- Invented numbers, wards, priorities, patients or nurse names. Only data the device actually sends.
- Any runtime network request beyond the Sonara server (no CDN, no web fonts from the internet).
- Heavy continuous effects on the board's room display (it is a 1024 x 600 kiosk on the UNO Q);
  showpieces like the start-up intro stay presentation-only.

## Type
- Inter only, bundled under `web/shared/fonts/`.
- Body at least 16px on the phone. Nurse UI uses a fixed scale. The patient headline is the only large type.
- Tabular numerals for wait times and bed numbers.

## Colour: 60-30-10
- 60% `--canvas`, 30% surfaces and dividers, 10% one accent per screen: the state colour on the
  patient screen, orange "new" on the nurse app.
- Every colour is a token in `:root` (`web/shared/base.css`). No literal colours below the token block.
- Status is never colour alone: always a word, and an icon where it helps.

## Spacing
- 4 / 8-point scale only (4, 8, 12, 16, 24, 32, 48, 64), as tokens. The patient screen uses
  mockup coordinates scaled by `--px`.
- Touch targets at least 44px on the phone.

## Motion
- `transform` and `opacity` only on HTML, never `transition: all`. Every animation has a reduced-motion fallback.
- Motion shows state (listening, thinking, sent), never decoration.

## States
- Every control has hover, active, focus-visible (3px ink ring, instant) and disabled.

## Honesty (from AGENTS.md, not negotiable)
- Never claim help is coming. "Notified" only after the caregiver screen's receipt, and a
  receipt is sent only for a request that is actually rendered on a visible screen.
- Delivery failure and disconnection are distinct, persistent states with the nurse-call fallback.
- Never claim speech is playing when it is only queued.
