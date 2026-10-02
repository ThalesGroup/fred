# Verification

Evidence for `rework-neutral-surface-scale` on branch `ui-theme-polish` (2026-10-02).

## Proven

- **Ramp (spec: Neutral ramp tint).** Every `--core-cold-grey-*` step except 0 and 100 was converted back from hex to CIE LCh: 0 failures against chroma ≤ 2, hue 280° ± 10° (max deviation 8.4°), |L\* − tone| ≤ 0.6.
- **Surface tones (spec: Surface tones).** Resolving each `--surface-*` token through `color-ramps.css` gives the spec table in both themes (light, after the "higher = lighter" revision: main 99.5, lowest → highest 93 / 94.5 / 96 / 97.5 / 100, floating 100; first pass was 100 / 99 / 97.5 / 96 / 94.5 / 93; dark 6 / 8 / 10 / 12 / 15 / 18, floating 20 — raised from 15 during the second pass, see design.md). The ordering scenarios follow from these values.
- **Floating surface.** Every CSS rule with `position: absolute|fixed`, a `--shadow`/`--elevation` box-shadow and a surface background uses `surface-floating`; chart and mind-map tooltips set from TSX do too.
- **Remaining `surface-container-lowest` / `-highest` usages.** All 45 match a role of the design.md table.
- **Package.** `npm run build:tokens` in `libs/frontend` succeeds; `dist/tokens.css` defines `--surface-floating`.
- **Quality gate** (same commands as `make code-quality`, run directly in `apps/frontend` so the running Vite keeps its cache): `npx tsc --noEmit` OK, Prettier check OK on changed files, ESLint OK on changed TS/TSX.
- **Tests:** `npm run applications:test` OK; `npx vitest run` 3159 passed, 4 failed, 7 skipped. The 4 failures (`src/rework/core/hooks/useChatSse.test.tsx`, first-turn `ask_user` availability) fail identically on `swift` without this change.
- **Migration note:** `make migration-check MIGRATION_BASE=swift` → "Migration notes valid: 1 new declaration(s)".
- **Second pass (tasks section 5):** every hover/focus rule with a surface background listed and classified; layered state-over-base hovers left untouched; no surface usage inside a re-tokened card equals the card token.
- **Review:** `/code-review` on `swift...HEAD` found 3 issues (fills nested in floating surfaces, chart tooltips set from TSX); all fixed in `2b7289869`, and a second `/code-review` on that commit found none. A `/code-review` of the second pass plus the foreground change found 3 issues (form-control borders merged into the divider token, two hovers equal to their resting border), fixed in `dbcc6baf4`; its re-review found none.

## Not proven

- Computed values were not read in a browser; the in-app check in both themes is left to the developer on the running Vite.
- Contrast ratios of text on the new surfaces were not measured (text tokens are out of scope; tones are unchanged, hue only).
