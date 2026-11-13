# ui design rules

> **2026-11-13, user decision:** the v2 light mockup is the spec and wins where it clashes with these rules
> (Inter and the purple listening/confirm accents are allowed; no character on the patient screen).
> The honesty rules at the bottom still bind.

Binding for every change in `web/`. Checked with the Hallmark linter (`sloplint`) and the
Impeccable / anti-ui-slop skills before each push.

## Banned
- Inter as a typeface. Purple or purple-to-blue gradients. Glowing spheres or orbs, floating glass cards, backdrop blur.
- Emoji as icons. Cards inside cards. Eyebrow labels or tracked all-caps labels. Decorative status dots.
- Invented numbers, wards, patients or nurse names. Only data the device actually sends.
- Any runtime network request beyond the Sonara server (no CDN, no web fonts from the internet).

## Type
- One display face, bundled as a file under `web/shared/fonts/`. Body text in the same family or the system face.
- Body 16 to 18px. Nurse UI uses a fixed scale (ratio 1.125 to 1.2). Patient headline is the only large type.
- Tabular numerals for wait times and bed numbers.

## Colour: 60-30-10
- 60% one neutral background. 30% a second neutral for structure (bars, rows, panels). 10% one accent, only on the primary action, the current state and the active selection.
- Every colour is a token in `:root`. No literal colours below the token block.
- Status is never colour alone: always a word, and an icon where it helps.
- Palette taken from a real reference (photo or product screenshot), not invented.

## Spacing
- 8-point scale only: 8, 16, 24, 32, 48, 64 (4 allowed for hairline nudges). Tokens, never raw lengths.

## Motion
- `transform` and `opacity` only, never `transition: all`. Every animation has a reduced-motion fallback.
- Motion shows state (listening, sent), never decoration.

## Honesty (from AGENTS.md, not negotiable)
- Never claim help is coming. "Notified" only after the caregiver screen's receipt.
- Delivery failure and disconnection are distinct, persistent states with the nurse-call fallback.
