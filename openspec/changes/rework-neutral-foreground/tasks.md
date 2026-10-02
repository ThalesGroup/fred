## 1. Tokens

- [x] 1.1 Add `--core-cold-grey-45` with the ramp formula; verify chroma ≤ 2 and hue within 10° of 280°
- [x] 1.2 Set text tones (light 10 / 40 / 45, dark 95 / 75 / 60) and outline tones (light 50 / 80 / 88, dark 60 / 40 / 30); remove `--outline-retreat`; verify contrast ratios with a script against every surface level
- [x] 1.3 Remove the `--color-*` aliases and `--state-surface-main-{hover,pressed,focused,selected}`; verify no reference remains

## 2. Usages

- [x] 2.1 Replace every `--outline-retreat` reference (CSS and TSX) with `--outline-muted`; verify zero references remain and chart var lists have no duplicates
- [x] 2.2 Move DataTable cell and TablePagination footer borders from `--surface-container-highest` to `--outline-muted`; verify a table in both themes
- [x] 2.3 Repoint undefined tokens (`--on-surface-variant`, `--text-secondary`, `--text-tertiary`, `--color-on-surface-retreat`, `--core-primary`); verify with an undefined-token scan

## 3. Quality and docs

- [x] 3.1 Run type-check, Prettier, ESLint and vitest; verify they pass (known `useChatSse` failures excepted)
- [x] 3.2 Update `FRONTEND_CODING_GUIDELINES.md`, `COMPONENT-UX.md`, `CHAT-COMPONENT-SPECS.md` and the design-tokens README migration section; fold the change into the branch migration note
- [ ] 3.3 Run `/code-review`, record evidence in `verification.md`
