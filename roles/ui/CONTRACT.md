# ui CONTRACT: what speech and device may rely on

`config/intents.toml`:
- `[[intent]]` entries: `id` (UPPER_SNAKE, stable), `label`, `speak`, `notify`, optional `control`.
- `[prompts]`: fixed system sentences keyed by name (`didnt_understand`, `ask_send`, `sending`, `cancelled`,
  `displayed`, `acknowledged`, `completed`, `not_displayed`, `listening`).

Changing a `speak` text or prompt → `FYI` to `speech` (regenerate WAVs). Adding/removing an intent id →
`CONTRACT` to `speech` and `device`.
