# Verification

Evidence for `rework-neutral-foreground` on branch `ui-theme-polish` (2026-10-02).

## Proven

- **Ramp step 45:** `#6a6b6d`, CIE L\* 45.2, chroma 1.26, hue 271.6° (within 10° of 280°).
- **Text contrast (spec: Text tones):** scripted over the token files. Light: `on-surface-retreat` ≥ 5.44:1 on every surface level, `on-surface-muted` 5.33:1 on `surface-main`. Dark: `on-surface-retreat` ≥ 7.12:1 on every surface level, `on-surface-muted` 5.90:1 on `surface-main`. `outline` on `surface-main`: 4.48:1 light, 5.90:1 dark.
- **Three outline levels:** no `--outline-retreat` definition or reference in `apps/frontend/src`; the rebuilt `@fred-oss/design-tokens` `dist/tokens.css` has none either. Chart var lists have no duplicate entries.
- **Undefined tokens:** a scan of `var(--…)` color references finds only component-local properties set inline from TSX (`--badge-color`, `--dot-color`, `--button-group-background-color`, `--datatable-background-color`) and the non-color `--icon-invert` / `--primary-hue` with fallbacks.
- **Quality gate:** `npx tsc --noEmit`, Prettier check and ESLint on changed files pass; `npx vitest run` 3159 passed, 4 failed (pre-existing `useChatSse.test.tsx` failures, identical on `swift`).
- **Migration note:** folded into `neutral-surface-scale.md`; `make migration-check MIGRATION_BASE=swift` → valid, 1 declaration.
- **Review:** `/code-review` found that merging `outline-retreat` into `outline-muted` collapsed form-control borders onto the divider tone and erased two hover steps; fixed (`dbcc6baf4`), re-review clean.

## Not proven

- Rendering in a browser in both themes is left to the developer on the running Vite.
