# Tasks

## 1. Theme-local tab metadata

- [x] 1.1 Extend the custom catalog type, browser validation and shared installer validation; verify valid/omitted metadata and malformed title/path cases with focused catalog and overlay tests.
- [x] 1.2 Update the existing tab effect to resolve active-theme title and light/dark favicons; verify Paris-to-Pebble and mode transitions with a browser-DOM test. Document the optional fields in the frontend README and existing operator migration note.

## 2. Settings synchronization and administration

- [x] 2.1 Connect the provider to the generated public-config query, existing settings tag invalidation and cross-session refresh helpers; verify successful saves, hidden custom selection, single offered custom theme, focus refresh and network failure using provider/API tests. Update the existing next-load documentation to describe refresh behavior.
- [ ] 2.2 Replace the default disabled button with a visible status, improve availability/preview labels and responsive tile layout; verify saved/default/hidden states in admin component tests and inspect light/dark rendering at narrow width.

## 3. Local integration and review

- [ ] 3.1 Add metadata to the personal Paris ZIP outside Git, retain neutral global translations, upload it to local SeaweedFS and restart Vite; verify localhost:5173 serves the updated archive and the tab/theme transitions during local validation.
- [ ] 3.2 Run affected tests, TypeScript and formatting checks; apply author review and independent read-only review to the updated PR delta, record findings and limitations in PR #3028, and verify only authorized files are committed and pushed.

## Verification notes

- 1.x/2.1: `make code-quality` green; `make test` green except `PlatformAccessPage` "grants more than 100 selections", which also exceeds its 5 s timeout on `swift` under coverage (pre-existing, unrelated).
- The provider now imports the generated API slice, so tests mocking `controlPlaneOpenApi` must keep the real module (`importOriginal`).
- 2.2 is open until light/dark rendering is inspected at narrow width; 3.1 is open while the personal ZIP is being edited.

## Workflow follow-up

- After developer approval, apply this change on feat/ui-theme-customization.
- Sync delta specs and archive after verification and required review.
