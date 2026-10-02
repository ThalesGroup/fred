## Why

Follow-up to `rework-neutral-surface-scale` (#2915). Secondary text in the light theme is near-black (`on-surface-retreat` at tone 30, the most used color token of the app), which makes the light theme read hard and heavy. The dark `on-surface-muted` (tone 50) is below WCAG AA on the page. Outlines have four tokens for three visible values (`outline-retreat` and `outline-muted` are identical in light), so the choice between them is arbitrary. The token files also carry dead aliases and some components use tokens that are not defined at all.

## What Changes

- Text tones: light `on-surface` 10 / `on-surface-retreat` 40 / `on-surface-muted` 45 (new ramp step); dark 95 / 75 / 60.
- Outlines: three levels instead of four. `outline` light 50 / dark 60, `outline-variant` light 80 / dark 40, `outline-muted` light 88 / dark 30. **BREAKING** for `@fred-oss/design-tokens` consumers: `--outline-retreat` is removed; form controls use `--outline-variant`, containers and dividers `--outline-muted`.
- Borders drawn with `--surface-container-highest` (DataTable cells, TablePagination) move to `--outline-muted`.
- Remove dead tokens: the `--color-*` alias layer and `--state-surface-main-{hover,pressed,focused,selected}` (no usage).
- Fix undefined tokens in use: `--on-surface-variant`, `--text-secondary`, `--text-tertiary`, `--color-on-surface-retreat`, `--core-primary`.

Non-goals: accent roles (primary, secondary, tertiary, status colors) are a separate change.

## Capabilities

### New Capabilities

- `frontend-neutral-foreground`: the neutral text and outline tokens of the Fred frontend.

### Modified Capabilities

None.

## Impact

- `apps/frontend/src/styles/` (ramp, semantic light/dark, state tokens) and every usage of `--outline-retreat` (CSS and chart TSX).
- `@fred-oss/design-tokens`: one token removed, several removed aliases; README "Token migrations" updated.
- Docs: `FRONTEND_CODING_GUIDELINES.md`, `COMPONENT-UX.md` token table, `CHAT-COMPONENT-SPECS.md` mockup table, migration note.
