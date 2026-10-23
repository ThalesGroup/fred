## 1. Database and self-service API

- [x] 1.1 Create the Control Plane-owned `users_preferences` table in one Alembic migration; verify one Alembic head and a real upgrade to head.
- [x] 1.2 Add a typed store with absent-row defaults, atomic partial updates, pane-width merge and deletion; verify round-trip, validation boundaries, isolation and deletion in focused tests.
- [x] 1.3 Add authenticated `GET` and `PATCH /users/me/preferences` and account-deletion cleanup; verify self-only access, defaults and invalid-input behavior in focused API tests.

## 2. Browser hydration and controls

- [x] 2.1 Regenerate the Control Plane OpenAPI client and wire generated preference endpoints; verify the generated types match the backend schema.
- [x] 2.2 Hydrate preferences before signed-in content paints, importing validated legacy localStorage values only for an absent row; verify browser wipe, account switch, failed read, import success/failure and stable theme resolution in focused tests.
- [x] 2.3 Persist theme, mode, language and sidebar changes through partial updates; verify each control restores its confirmed state after a browser wipe and errors do not leave a false saved choice.
- [x] 2.4 Persist team and agent sorts, trace expansion and named pane widths on drag end; verify every stored value restores from the database and rapid drag avoids per-move requests.

## 3. Documentation and completion

- [x] 3.1 Document stable theme IDs, the personal preference API and browser import limits in the theme guide and product contract; verify docs match implemented behavior.
- [x] 3.2 Add the required English operator migration note and verify `make migration-check` passes.
- [ ] 3.3 Run root `make code-quality`, relevant offline tests and the branch review procedure, resolve findings, then reconcile and archive the OpenSpec change; record exact results in the draft PR.
- [x] 3.4 Exercise several settings for one local test user and show the resulting `users_preferences` row; verify it includes all persisted fields.
