# Tasks

## 1. Confirm scope and tracking

- [x] 1.1 Obtain developer confirmation of this proposal, design and acceptance scenarios; create a dedicated tracking issue and record its link here before implementation. Approved on 2026-10-15; tracking: [#3133](https://github.com/ThalesGroup/fred/issues/3133). Implementation uses the requested separate worktree on `codex/keycloak-local-login`, based on `origin/swift` at `e44837560`.

## 2. Implement the one-time entry flag

- [x] 2.1 Consume exact `keycloak-login=true` on initial authenticated-mode entry in `OidcBrowserSession` without a provider-setting or issuer-shape check, clean browser history and keep the cleaned return route in local state; verify SDK-generated authorization contains an explicitly empty `kc_idp_hint`, `prompt=login`, opaque state and PKCE S256 for both provider settings, including Keycloak configured through generic OIDC.
- [x] 2.2 Prioritize the explicit request over a cached Fred user, clear previous local credentials and retain generation protection without provider logout; verify stored-user switching, late results, callback priority, callback restoration and reload without another forced login.
- [x] 2.3 Keep ordinary sign-in without opt-in for both provider settings, false/empty flags, insecure mode, invitation-route privacy, refresh and logout compatible; verify focused browser-session/facade regression suites and explicit requests to an issuer without Keycloak-specific behavior.

## 3. Document and verify integration

- [x] 3.1 Add a usage section to `docs/swift/platform/KEYCLOAK.md` and the required English migration note; verify they describe deep links, the exact flag, both provider settings, one-time behavior, local credentials, organization/form fallback, non-Keycloak issuer limitations and unchanged permission enforcement.
- [ ] 3.2 Run focused authentication tests and changed-file formatting checks; record commands/results here and follow the draft PR's CI through its broad quality/test checks, as requested by the developer. Manually check normal SSO and explicit local login with a compatible real Keycloak flow, or state explicitly if that environment is unavailable.
- [x] 3.3 Run the author branch review against `swift` and obtain a fresh independent read-only review of requirements, implementation and affected auth consumers; record base/head, findings/dispositions and exclusions here or in the draft PR.

## 4. Deliver and reconcile

- [ ] 4.1 Commit completed blocks, push and open a draft PR linked to the tracking issue; verify the final diff contains only this follow-up and attach the PR to the chat.
- [ ] 4.2 Reconcile artifacts with verified implementation and sync/archive this change using the repository procedures; preserve the existing frontend-oidc-login lifecycle requirements and do not archive or mark complete the portability parent's pending manual checks.

## Verification and review (2026-10-15)

- Focused command: `cd apps/frontend && ./node_modules/.bin/vitest run src/security/OidcBrowserSession.test.ts src/security/KeycloakService.oidc.test.ts` - 80 tests passed in two files. Tests exercise actual SDK authorization serialization, both provider settings, cached sessions, callback/reload, invitation privacy, stale renewal/callback/timeout behavior, storage failure and insecure mode.
- Changed-file Prettier check, `git diff --check`, strict OpenSpec validation and root `make migration-check` passed. The migration declaration is minor because optional use may require an external Keycloak Browser flow change.
- Local `tsc --noEmit` stopped on missing `@dnd-kit/core`, `@dnd-kit/sortable` and `@dnd-kit/utilities` in reused dependencies, in unrelated existing Announcements files. No dependency or lockfile change is included. The CI TypeScript result will be authoritative.
- Developer explicitly delegated broad tests/code quality to CI; they were not run locally. CI results are pending. No real Keycloak tenant/browser walkthrough was available for this implementation; the server-side escape hatch was manually verified by the developer before this feature.
- Author review and independent fresh-context read-only review covered the full working-tree delta against target `swift`, merge base `e44837560`, including authentication source, tests, guide, migration note, OpenSpec, bootstrap/configuration, facade, AuthContext and bearer consumers. No actionable findings remained. Review excludes real IdP verification and broad CI; the subsequent source comment changes no behavior.
