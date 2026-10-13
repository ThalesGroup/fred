## 1. Backend filter and ordering

- [x] 1.1 Add the `exceptions_only` filter and the alphabetical order to the store's user page and count; verify with fred-core tests covering filter on/off, total, ordering (case, missing username, id tiebreak), pagination and search combined with the filter.
- [x] 1.2 Expose `exceptions_only` on `GET /admin/platform/access/users` and pass it through the service; verify with control-plane tests on the service page and on the HTTP route (default unchanged, filtered total, order).

## 2. Generated contract

- [x] 2.1 Regenerate the backend `openapi.json` and `controlPlaneOpenApi.ts`; verify the diff contains only the new optional parameter.

## 3. Whitelist list

- [x] 3.1 Make the Users sub-tab list individual exceptions only (filter on, 20 per page by default with a 20/50/100 selector, real total, debounced search), with "Remove" and its toast, without row selection or bulk bar; verify with page tests (query arguments, removal, loading and failed states).
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
- [x] 7.3 Show "Added on", "Origin" and "Other access" in the whitelist table; verify with page tests for the date cell and origin of both origins and the other access limited to the other sources (shown since section 8 as one chip, with an empty cell when there is none).
- [x] 7.4 Add the French and English strings and delete the unused ones; verify key parity and that no deleted key is referenced.
- [x] 7.5 Update the contract entry, `COMPONENT-UX.md` and the migration note; record the evidence below and re-run `openspec validate whitelist-lists-individual-exceptions --strict`.
- [x] 7.6 Title the Users block with a heading above the toolbar and reword the search (an `h3` at the time, an `h2` since section 10); verify with a page test that the heading is the panel's first element and the only heading in it.

## 8. One navigation level, whitelist wording, compact other access

- [x] 8.1 Replace the Whitelist tab and its sub-tabs by top-level Users and Teams tabs, each with a title (an `h2` since section 10) and a description above its controls; verify with page tests (three tabs, one exposed panel, keyboard navigation, users request skipped on other tabs, draft/search/page preserved, header action present on each tab). The page-size part had no test until section 10 added "changes the users page size from the first page, asking for the new limit".
- [x] 8.2 Show other access as one chip with a grouped tooltip and an empty cell otherwise; verify with page tests (one chip per row with other access, none without, grouped content for each kind and several teams, focusable trigger with an accessible name).
- [x] 8.3 Reword the French strings to "de la liste blanche" and delete unused keys; verify key parity and that no deleted key is referenced.
- [x] 8.4 Update `COMPONENT-UX.md`, record the evidence and re-run `openspec validate whitelist-lists-individual-exceptions --strict`.

## 9. Accent-insensitive searches

- [x] 9.1 Fold accents and case in the server-side user search with a shared SQL construct (the typed text is folded by the same construct since section 10); verify with fred-core tests (accent on either side and both, mixed case, with the exception filter, symbols and other scripts unchanged, PostgreSQL expression compiled).
- [x] 9.2 Fold accents and case in the teams filter and the account-field picker with the existing `stripDiacritics`; verify with page tests (match, no-match line, clear) and a picker test.
- [x] 9.3 Update the contract entry, `COMPONENT-UX.md` and the migration note; record the evidence and re-run `openspec validate whitelist-lists-individual-exceptions --strict`.

## Verification evidence (2026-10-13)

Nothing visual was checked: the page and the dialog were not rendered in a browser, and the running control-plane was not restarted, so the new filter was not exercised against a live backend or PostgreSQL.

Backend, from `libs/fred-core` (tools from its `.venv/bin`):

- `make test`: 1248 passed, 1 skipped, 42 deselected. New test `test_user_listing_orders_by_username_and_filters_individual_exceptions` (filter on/off, totals, case-insensitive order, missing usernames last, id tiebreak, pagination, search combined with the filter).
- `ruff check`, `ruff check --select I`, `ruff format --check`: all pass. `basedpyright --baseline-file .baseline/basedpyright-baseline.json`: 0 errors.

Backend, from `apps/control-plane-backend`:

- `make test`: 1788 passed, 9 skipped (the PostgreSQL-backed platform access tests, which need a database), 11 deselected. New test `test_users_listing_restricts_to_individual_exceptions_in_username_order` (service page in both modes, sources, pagination, search with the filter, and the HTTP route with and without `exceptions_only`).
- `ruff check`, `ruff check --select I`, `ruff format --check`: all pass. `basedpyright --baseline-file .baseline/basedpyright-baseline.json`: 0 errors.
- The ordering and the filter ran on SQLite only. `lower(username) ASC NULLS LAST` and the filter (an `EXISTS` at that date, an inner join since section 7) are standard SQL, but the result on PostgreSQL (whose text order follows the database collation) was not run.

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
- `make migration-check` (repository root): "Migration notes valid: 2 new declaration(s)". At that date the second note was the entry-pages one, then carried by the same local branch; the branch is now stacked on #3087 only and the second declaration is that change's note (see the section 10 evidence).
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

## Verification evidence for section 8 (2026-10-14)

Frontend only; nothing visual was checked (tab row, titles, chip, tooltip placement and the focus ring on the chip wrapper were not seen in a browser).

From `apps/frontend`, no make target:

- `npx tsc --noEmit`: exit 0. `npx eslint src/rework/components/pages/admin/PlatformAccessPage`: exit 0. `npx prettier --config .prettierrc --check` on that folder and both `translation.json`: pass.
- `npx vitest run`, one file at a time: `PlatformAccessPage.test.tsx` 33 passed; `PlatformAccessAddUsersDialog.test.tsx` 9, `PlatformAccessRuleEditor.test.tsx` 34 and `PlatformAccessLinkManager.test.tsx` 27 passed, unmodified.
- Page tests rewritten for this section: one tablist of three tabs with matching `aria-controls` / `aria-labelledby`, one exposed panel at a time, arrow-key navigation through the three tabs, header filtering action present on each; title then description as the first element of the Users and Teams panels, before any control; users request skipped on the Rules and Teams tabs; rule draft, search and page preserved across the three tabs; one focusable chip per row with other access, its accessible name and its tooltip listing rule, administrator, two authorized teams on one line and the link-access team; a single-kind row; an empty cell without chip for a row with no other access.
- No shared component was changed. `Chip` has a single size and accepts neither focus nor ARIA props; it is wrapped, not extended.
- `rework.platformAccess` exposes the same 223 keys in French and English; `whitelistTabs.*`, `whitelistHint`, `teamHint`, `source.*` and `otherSources` are removed and no longer referenced.
- `openspec validate whitelist-lists-individual-exceptions --strict`: valid.

## Verification evidence for section 9 (2026-10-14)

Not run: anything in a browser, and the PostgreSQL path against a real server (the running control-plane keeps the previous code until restarted; the PostgreSQL-backed tests need `FRED_PLATFORM_ACCESS_TEST_DATABASE_URL`).

- `libs/fred-core`: `make test` 1250 passed, 1 skipped, 42 deselected; `ruff check`, `ruff check --select I`, `ruff format --check` pass; `basedpyright --baseline-file .baseline/basedpyright-baseline.json` 0 errors. `test_user_search_ignores_accents_and_case_on_both_sides` (SQLite): accent on the stored side, on the query side, on both, mixed case, a letter typed as base + combining mark, every column still searched, combined with `exceptions_only`, total equal to the rows, symbols and `%` as before, Cyrillic, ligatures matching only themselves. `test_accent_folding_table_and_postgresql_expression`: the letters listed in the request and their upper cases fold to their base, and the PostgreSQL statement compiles to four `translate(lower(users.…))` with the folded pattern and no `replace`.
- `apps/control-plane-backend`: `make test` 1788 passed, 10 skipped (PostgreSQL-backed, including the new `test_pg_user_search_ignores_accents_and_case`), 11 deselected; same four lint and type checks clean.
- `apps/frontend`, no make target: `npx tsc --noEmit` exit 0; `npx eslint src/rework/components/pages/admin/PlatformAccessPage` exit 0; prettier check passes on that folder; `npx vitest run`, one file at a time: `PlatformAccessPage.test.tsx` 34 passed (one added: teams filter with accents either side, case, unnamed team, no-match line, clear), `PlatformAccessRuleEditor.test.tsx` 34 passed (picker search extended with an accented query), `PlatformAccessAddUsersDialog.test.tsx` 9 and `PlatformAccessLinkManager.test.tsx` 27 passed, unmodified.
- No response shape change: the generated client was not regenerated.
- `openspec validate whitelist-lists-individual-exceptions --strict`: valid.

## 10. Pre-PR review fixes

- [x] 10.1 Keep one "page emptied" mechanism: the page-level step back is removed and the shared `DataTable` clamp alone moves the offset; verify with the page test "steps back a single page when a removal empties the last page" (three pages: page 3 lands on page 2).
- [x] 10.2 Render the teams table only when there is something to show, instead of a `hidden` attribute its flex class overrode; verify with "narrows the teams table ignoring accents and case, says when nothing matches, and clears" (no table under the no-match line).
- [x] 10.3 Fold the typed search text in SQL through the same construct as the columns, as bind parameters; Python only composes it (NFC) and adds the lower-case spelling of a query holding a capital an ASCII-only `lower()` would keep. Verify with `test_user_search_finds_stored_capitals_outside_the_folding_table`, `test_search_spellings_leave_the_folding_to_the_database` and the updated `test_accent_folding_table_and_postgresql_expression`.
- [x] 10.4 Request the teams listing on the Teams tab only and the initial-import preview on the Users tab only, so the spec sentence "no listing SHALL be requested for a tab that is not shown" is true; verify with "requests the teams listing and the import preview only for the tab that shows them". Nothing else on the page reads teams data: the Users table takes team names from its own rows, and the activation dialog issues its own queries.
- [x] 10.5 After a successful add, clear the search and return to the first page; verify with "returns to the first page of the unfiltered list after an add, where the newest are listed" and "keeps the page and the search after a failed add".
- [x] 10.6 Build the "Other access" accessible name from a localized sentence and separator (fr, en); verify with the assertions added to "shows when and how each individual access was added, and one chip detailing the other access".
- [x] 10.7 Make the two block titles `h2`, like Conditions after #3087's review fix; verify with "titles each whitelist tab and describes it above its controls".
- [x] 10.8 Add the missing test of the users table page size ("changes the users page size from the first page, asking for the new limit": options 20/50/100, first page, new limit, size kept across tabs) and make design.md, this file, the delta spec, the migration note and `COMPONENT-UX.md` describe the shipped state.
- [x] 10.9 Record four reviewer questions in design.md (cost of a 100-row page, removal without confirmation, the hand-rolled dialog shell, a disabled first suggestion in the shared `Autocomplete`). Not implemented.

## Verification evidence for section 10 (2026-10-14)

Run on the branch restacked on `feat/platform-access-ui-condense` (plain `git rebase`, after that branch's own review fixes). Not run: anything in a browser; the PostgreSQL path against a real server (the PostgreSQL-backed tests need `FRED_PLATFORM_ACCESS_TEST_DATABASE_URL` and were skipped), so the SQL-side folding of the search text ran on SQLite and was only compiled for PostgreSQL.

- `apps/frontend`: `make code-quality` (tsc, prettier, eslint) exit 0; `make test` (full vitest suite with coverage) 331 files passed, 1 skipped; 4139 tests passed, 7 skipped. `npx vitest run src/rework/components/pages/admin/PlatformAccessPage`: 4 files, 111 tests passed.
- `libs/fred-core`: `make test` 1252 passed, 1 skipped, 42 deselected; `ruff check`, `ruff check --select I`, `ruff format --check` pass; `basedpyright --baseline-file .baseline/basedpyright-baseline.json` 0 errors.
- `apps/control-plane-backend`: `make test` 1788 passed, 10 skipped (PostgreSQL-backed), 11 deselected; the same four lint and type checks clean.
- `rework.platformAccess` exposes the same keys in French and English (221 leaf keys each by a recursive count, plural forms included).
- `make migration-check` (repository root): "Migration notes valid: 2 new declaration(s)", this note and #3087's, which this branch is stacked on.
- `openspec validate whitelist-lists-individual-exceptions --strict`: valid.
- No response shape change: the generated client was not regenerated.

Behaviour to know about 10.3, on a database whose `lower()` is ASCII-only (SQLite; PostgreSQL under a C/POSIX `LC_CTYPE`): a letter outside ASCII and the folding table (Ł, Ø, Cyrillic, Greek) stored as a capital is found when typed as a capital, not when typed in lower case; stored in lower case it is found in either case. With a Unicode-aware `lower()` both cases match, as the PostgreSQL-backed test expects.
