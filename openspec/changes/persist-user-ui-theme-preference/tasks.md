## 1. Persistence and API

- [ ] 1.1 Add nullable theme ID and mode fields to the existing `users` row in one Alembic migration; verify `alembic heads` has one head and `alembic upgrade head` succeeds.
- [ ] 1.2 Add user-store read and atomic replace operations; verify missing-row defaults, round-trip values and account isolation with focused store tests.
- [ ] 1.3 Add authenticated `GET` and `PUT /users/me/ui-preferences` with bounded ID and mode validation; verify self-only access and invalid-input behavior with focused API tests.

## 2. Frontend

- [ ] 2.1 Regenerate the Control Plane OpenAPI client and wire its query/mutation through the existing enhancements module; verify generated types match the backend models.
- [ ] 2.2 Replace global personal-choice storage with an authenticated-user-scoped cache and database hydration gate, keeping the boot background and existing platform fallback rules; verify reload, new browser, API failure and account-switch cases with focused tests.
- [ ] 2.3 Persist profile picker changes and restore the confirmed choice on save failure; verify theme and mode selection, a hidden or missing saved ID, and error behavior with focused frontend tests.

## 3. Documentation and completion

- [ ] 3.1 Document stable catalog IDs and the personal preference API in the theme guide and product contract; verify docs agree with the implementation.
- [ ] 3.2 Add the required English operator migration note, including the one-time legacy browser preference reset; verify `make migration-check` passes.
- [ ] 3.3 Run root `make code-quality`, relevant offline tests and the branch review procedure, resolve findings, then reconcile and archive the OpenSpec change; record exact results in the draft PR.
