## 1. Backend filter and ordering

- [x] 1.1 Add the `exceptions_only` filter and the alphabetical order to the store's user page and count; verify with fred-core tests covering filter on/off, total, ordering (case, missing username, id tiebreak), pagination and search combined with the filter.
- [x] 1.2 Expose `exceptions_only` on `GET /admin/platform/access/users` and pass it through the service; verify with control-plane tests on the service page and on the HTTP route (default unchanged, filtered total, order).

## 2. Generated contract

- [x] 2.1 Regenerate the backend `openapi.json` and `controlPlaneOpenApi.ts`; verify the diff contains only the new optional parameter.

## 3. Whitelist list

- [x] 3.1 Make the Users sub-tab list individual exceptions only (filter on, 25 per page, real total, debounced search), with "Remove" and its toast, without row selection or bulk bar; verify with page tests (query arguments, removal, loading and failed states).
- [x] 3.2 Add the empty-whitelist state distinct from "no match"; verify with a page test for each.
- [x] 3.3 Check the rule tester still calls the users query without the filter; verify by its existing tests and by reading the call.

## 4. Add dialog

- [x] 4.1 Extract the shared `AddPeopleDialog` shell from `AddTeamMembersDialog` without changing the latter's props; verify its existing test file passes unmodified.
- [x] 4.2 Add the optional `noOptionsMessage` to `Autocomplete`; verify its existing tests pass and a new one covers the message.
- [x] 4.3 Build the whitelist add dialog on the shell (debounced search with the filter off, pending selection kept across searches, already-granted people disabled, bulk grant, toast, close); verify with dialog tests for each of those.

## 5. Copy

- [x] 5.1 Add the French and English strings and delete the unused keys; verify by grep that no deleted key is referenced and that both files expose the same keys under `rework.platformAccess`.

## 6. Docs and close-out

- [x] 6.1 Add the dated entry to `CONTROL-PLANE-PRODUCT-CONTRACT.md`, update the "Platform access screens" section of `COMPONENT-UX.md`, and check the Help Center content for pages describing this screen.
- [x] 6.2 Add the migration note.
- [x] 6.3 Record the exact verification evidence below and run `openspec validate whitelist-lists-individual-exceptions --strict`.

## 7. Grant date, origin and newest first

- [x] 7.1 Return each user with their exception row from the page query and order by grant date (newest first) under the filter; verify with fred-core tests (order with the filter, order unchanged without it, search with the filter, pagination stability, ties alphabetical).
- [x] 7.2 Use that row in the service projection instead of a per-row read; verify with control-plane tests that the individual source carries its grant date, that users without an exception carry none, and that no per-row exception read remains.
- [x] 7.3 Show "Added on", "Origin" and "Other access" in the whitelist table; verify with page tests for the date cell and origin of both origins, the filtered chips and the empty-cell marker.
- [x] 7.4 Add the French and English strings and delete the unused ones; verify key parity and that no deleted key is referenced.
- [x] 7.5 Update the contract entry, `COMPONENT-UX.md` and the migration note; record the evidence below and re-run `openspec validate whitelist-lists-individual-exceptions --strict`.
- [x] 7.6 Title the Users block with an `h3` above the toolbar and reword the search; verify with a page test that the heading is the panel's first element and the only `h3` in it.

## Verification evidence (2026-10-13)

Nothing visual was checked: the page and the dialog were not rendered in a browser, and the running control-plane was not restarted, so the new filter was not exercised against a live backend or PostgreSQL.

Backend, from `libs/fred-core` (tools from its `.venv/bin`):

- `make test`: 1248 passed, 1 skipped, 42 deselected. New test `test_user_listing_orders_by_username_and_filters_individual_exceptions` (filter on/off, totals, case-insensitive order, missing usernames last, id tiebreak, pagination, search combined with the filter).
- `ruff check`, `ruff check --select I`, `ruff format --check`: all pass. `basedpyright --baseline-file .baseline/basedpyright-baseline.json`: 0 errors.

Backend, from `apps/control-plane-backend`:

- `make test`: 1788 passed, 9 skipped (the PostgreSQL-backed platform access tests, which need a database), 11 deselected. New test `test_users_listing_restricts_to_individual_exceptions_in_username_order` (service page in both modes, sources, pagination, search with the filter, and the HTTP route with and without `exceptions_only`).
- `ruff check`, `ruff check --select I`, `ruff format --check`: all pass. `basedpyright --baseline-file .baseline/basedpyright-baseline.json`: 0 errors.
- The ordering and the filter ran on SQLite only. `lower(username) ASC NULLS LAST` and the `EXISTS` filter are standard SQL, but the result on PostgreSQL (whose text order follows the database collation) was not run.

Generated contract:

- `cd apps/control-plane-backend && make generate-openapi`, then from `apps/frontend` `npx --no-install @rtk-query/codegen-openapi src/slices/controlPlane/controlPlaneOpenApiConfig.json`. The diff of `controlPlaneOpenApi.ts` is the `exceptions_only` query parameter and the `exceptionsOnly?: boolean` argument only. `openapi.json` is git-ignored.

Frontend, from `apps/frontend` (no make target was run):

- `npx tsc --noEmit`: exit 0.
- `npx eslint` on `pages/admin/PlatformAccessPage`, `shared/organisms/AddPeopleDialog`, `TeamSettingsMembers/AddTeamMembersDialog`, `shared/molecules/Autocomplete`: exit 0.
- `npx prettier --config .prettierrc --check` on the same folders and both `translation.json`: all files pass.
- `npx vitest run`, one file at a time: `PlatformAccessAddUsersDialog.test.tsx` 9 passed (new); `PlatformAccessPage.test.tsx` 32 passed (updated); `AddTeamMembersDialog.test.tsx` 12 passed, file unmodified; `Autocomplete.test.tsx` 5 passed (one added); `PlatformAccessRuleEditor.test.tsx` 34 passed, file unmodified.
- Rule tester: `PlatformAccessRuleEditor.tsx` is not edited and still calls the users query with `{ offset: 0, limit: 100, query: username }`, without `exceptionsOnly`; it finds the administrator's row by id, so the new order does not affect it.
- `rework.platformAccess` exposes the same 219 keys in French and English; no reference remains to `allowSelected`, `clearSelection`, `selectedCount`, `noKnownUsers`, `allow` or `grantedUser`.

Docs:

- Help Center content (`apps/frontend/src/rework/features/helpCenter/content`, fr and en): no page describes this screen; nothing to update.
- `make migration-check` (repository root): "Migration notes valid: 2 new declaration(s)" (this note and the entry-pages note carried by the same local branch).
- `openspec validate whitelist-lists-individual-exceptions --strict`: valid.

Divergence from the proposal: none. The scenario "Return to an unsaved rule or selected users" keeps its name because a MODIFIED requirement cannot drop a scenario; its body now covers the user search.

## Verification evidence for section 7 (2026-10-14)

Nothing visual was checked, and the new order was not run against the live control-plane or PostgreSQL (the running service still serves the previous code until it is restarted).

- `libs/fred-core`: `make test` 1248 passed, 1 skipped, 42 deselected; `ruff check`, `ruff check --select I`, `ruff format --check` pass; `basedpyright --baseline-file .baseline/basedpyright-baseline.json` 0 errors. `test_user_listing_filters_individual_exceptions_and_orders_each_mode` covers the order with the filter (newest first, a shared date alphabetical), the unchanged order without it, search with the filter, pages of 3 and of 1 reproducing the full order, and each user paired with their own exception row or none.
- `apps/control-plane-backend`: `make test` 1788 passed, 9 skipped (PostgreSQL-backed), 11 deselected; same four lint and type checks clean. `test_users_listing_restricts_to_individual_exceptions_newest_first` covers the individual source carrying its grant date, no individual source for a user without an exception, identical sources with and without the filter, pagination, search with the filter, the HTTP route, and fails if the per-row exception read is called.
- SQL statements issued by one page of n rows: before, 3 + 2n (settings, page, count, and per row one exception read and one eligible-teams read); after, 3 + n. For the default page of 20: 43, then 23. The two authorization checks per row are unchanged.
- Generated contract: both regeneration commands were re-run; `controlPlaneOpenApi.ts` is unchanged, as the response shape did not change.
- `apps/frontend`: `npx tsc --noEmit` exit 0; `npx eslint src/rework/components/pages/admin/PlatformAccessPage` exit 0; `npx prettier --config .prettierrc --check` on that folder and both `translation.json` passes; `npx vitest run`, one file at a time: `PlatformAccessPage.test.tsx` 33 passed (one added: column order, date cell and origin for a manual and an imported access, chips limited to the other sources, "-" when there is none), `PlatformAccessAddUsersDialog.test.tsx` 9 passed, `PlatformAccessRuleEditor.test.tsx` 34 passed, `PlatformAccessLinkManager.test.tsx` 27 passed (the last three unmodified).
- `rework.platformAccess` exposes the same 221 keys in French and English; `sources`, `source.manual` and `source.t0` are removed and no longer referenced. The rule tester uses `rule.accessSource.*` and the activation dialog shows no source label, so neither is affected.
- `openspec validate whitelist-lists-individual-exceptions --strict`: valid.

Divergence from the request: no top-level grant-date field was added to the user, because the individual source of each row already carries `granted_at`; see design.md.

Block title (task 7.6), from `apps/frontend`: `npx tsc --noEmit` exit 0; `npx eslint src/rework/components/pages/admin/PlatformAccessPage` exit 0; prettier check passes on that folder and both `translation.json`; `npx vitest run src/rework/components/pages/admin/PlatformAccessPage/PlatformAccessPage.test.tsx` 33 passed (the former "no heading" test now checks the `h3`, its text and its position). `rework.platformAccess` then exposes 222 keys in each language.
