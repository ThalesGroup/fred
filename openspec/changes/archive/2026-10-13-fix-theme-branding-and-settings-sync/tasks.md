# Tasks

## 1. Theme-local tab metadata

- [x] 1.1 Extend the custom catalog type and shared installer validation; verify valid/omitted metadata and malformed title/path cases with overlay tests.
- [x] 1.2 Update the existing tab effect to resolve active-theme title and light/dark favicons; verify theme and mode transitions with a `uiThemeTab` unit test. Document the optional fields in the frontend README and existing operator migration note.

## 2. Settings synchronization and administration

- [x] 2.1 Connect the provider to the generated public-config query, existing settings tag invalidation and cross-session refresh helpers; verify successful saves, hidden custom selection, single offered custom theme, focus refresh and network failure using provider/API tests. Update the existing next-load documentation to describe refresh behavior.
- [x] 2.2 Replace the default disabled button with a visible status, improve availability/preview labels and responsive tile layout; verify saved/default/hidden states in admin component tests and inspect light/dark rendering at narrow width.

## 3. Local integration and review

- [x] 3.0 Implement structured theme ZIP assembly and archive-builder validation while retaining flat ZIP support; move the example into `themes/acme/` and `shared/`, update the English/French guides and README, and verify multi-theme assembly, image collisions, invalid folders and legacy archives.

- [x] 3.1 Add metadata to the personal Paris ZIP outside Git, retain neutral global translations, upload it to local SeaweedFS and restart Vite; verify localhost:5173 serves the updated archive and the tab/theme transitions during local validation.
- [x] 3.2 Run affected tests, TypeScript and formatting checks; apply author review and independent read-only review to the updated PR delta, record findings and limitations in PR #3028, and verify only authorized files are committed and pushed.

## Verification notes

- 1.x/2.1: `make code-quality` green; `make test` green except `PlatformAccessPage` "grants more than 100 selections", which also exceeds its 5 s timeout on `swift` under coverage (pre-existing, unrelated).
- The provider now imports the generated API slice, so tests mocking `controlPlaneOpenApi` must keep the real module (`importOriginal`).
- Structured ZIP verification: 14 overlay Node tests and 11 admin tests pass; the bundled example installs and serves its expected files; TypeScript, changed-file ESLint/Prettier, shell syntax, `git diff --check`, and strict OpenSpec validation pass. Independent review found a builder/installer validation mismatch; the builder now rejects unsupported shared entries and image path conflicts. Root `make code-quality` cannot start because `uv` is unavailable in this environment.
- 2.2 and 3.1 were validated by the developer (light/dark narrow-width rendering; Paris ZIP served by local Vite with tab/theme transitions).
- Final PR check (5dd2c9f23): `apps/frontend` `make code-quality` passes (tsc, Prettier, ESLint); `make test`: 3970 passed, 1 failed (`PlatformAccessPage` "grants more than 100 selections", 5 s timeout under coverage, outside this PR; passes alone, 24/24); 14 overlay Node tests pass; shell syntax of installer, builder and entrypoint passes.

## Workflow follow-up

- After developer approval, apply this change on feat/ui-theme-customization.
- Sync delta specs and archive after verification and required review.
