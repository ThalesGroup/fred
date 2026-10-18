## 1. Restore the shared account journey

- [ ] 1.1 Reconnect Profile and configured support in `UserProfile` using the sidebar's admitted state; verify identity/logout and Escape/focus behavior before admission, and keyboard navigation to `/settings` afterward.
- [ ] 1.2 Adapt the existing `UserSettingsPage` in place to manager `/me` roles, retaining identity/preferences/logout and removing mounted Python bootstrap/photo dependencies; verify owner-without-spaces, ordinary member, empty roles, pending/error and account-switch cases with focused tests.
- [ ] 1.3 Register `/settings`, `/gcu`, `/gdpr` and `/release-notes` under the existing guards, reusing the existing pages and accepted CGU content; verify direct URLs, return links, no repeated consent mutation, and unsupported-route fallback.

## 2. Validate behavior and reuse

- [ ] 2.1 Run the manual recipe with the developer before the automated campaign: owner without spaces opens Profile, sees `platform_owner`, changes language/theme/mode, reads all three linked pages, reloads and logs out; record observations and any deviations in this task response.
- [ ] 2.2 Extend existing frontend component/router tests and `tests/provisioning-browser.mjs` for the new routes, imported-account isolation and zero Python consumer requests; verify focused tests and `make -C apps/frontend test-provisioning-browser`, including desktop/narrow screenshots and unchanged import/replay behavior.
- [ ] 2.3 Verify applicable repository quality checks, including root `make code-quality` and the manager step gates required by `AGENTS.md`; record exact commands and results without claiming this focused recipe proves full Fred readiness.
- [ ] 2.4 Obtain an independent read-only review of the account-page lot, fix actionable findings with regression coverage and have corrections reviewed; record base/head, covered consumers, dispositions and exclusions, and verify no copied page/styles or new backend/storage contracts were introduced.

## 3. Reconcile and preserve the lot

- [ ] 3.1 Update implemented behavior in arc42 chapters 02, A1 and 09, the relevant existing UX guidance and the eventual PR migration note; verify `make -C docs/architecture check` and reconcile this change with the actual result.
- [ ] 3.2 Validate/sync/archive the completed OpenSpec change through the repository procedures and commit the reviewed step on `chore/rust-rebac`; verify a clean scoped diff and recorded checks, preserving unrelated changes and requiring explicit developer agreement before any push.
