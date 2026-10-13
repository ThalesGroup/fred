## 1. Backend filter and ordering

- [ ] 1.1 Add the `exceptions_only` filter and the alphabetical order to the store's user page and count; verify with fred-core tests covering filter on/off, total, ordering (case, missing username, id tiebreak), pagination and search combined with the filter.
- [ ] 1.2 Expose `exceptions_only` on `GET /admin/platform/access/users` and pass it through the service; verify with control-plane tests on the service page and on the HTTP route (default unchanged, filtered total, order).

## 2. Generated contract

- [ ] 2.1 Regenerate the backend `openapi.json` and `controlPlaneOpenApi.ts`; verify the diff contains only the new optional parameter.

## 3. Whitelist list

- [ ] 3.1 Make the Users sub-tab list individual exceptions only (filter on, 25 per page, real total, debounced search), with "Remove" and its toast, without row selection or bulk bar; verify with page tests (query arguments, removal, loading and failed states).
- [ ] 3.2 Add the empty-whitelist state distinct from "no match"; verify with a page test for each.
- [ ] 3.3 Check the rule tester still calls the users query without the filter; verify by its existing tests and by reading the call.

## 4. Add dialog

- [ ] 4.1 Extract the shared `AddPeopleDialog` shell from `AddTeamMembersDialog` without changing the latter's props; verify its existing test file passes unmodified.
- [ ] 4.2 Add the optional `noOptionsMessage` to `Autocomplete`; verify its existing tests pass and a new one covers the message.
- [ ] 4.3 Build the whitelist add dialog on the shell (debounced search with the filter off, pending selection kept across searches, already-granted people disabled, bulk grant, toast, close); verify with dialog tests for each of those.

## 5. Copy

- [ ] 5.1 Add the French and English strings and delete the unused keys; verify by grep that no deleted key is referenced and that both files expose the same keys under `rework.platformAccess`.

## 6. Docs and close-out

- [ ] 6.1 Add the dated entry to `CONTROL-PLANE-PRODUCT-CONTRACT.md`, update the "Platform access screens" section of `COMPONENT-UX.md`, and check the Help Center content for pages describing this screen.
- [ ] 6.2 Add the migration note.
- [ ] 6.3 Record the exact verification evidence below and run `openspec validate whitelist-lists-individual-exceptions --strict`.
