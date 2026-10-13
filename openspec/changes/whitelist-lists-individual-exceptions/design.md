## Context

See proposal.md for motivation. `PlatformAccessStore.users()` selects `UserRow` with an optional four-column `ILIKE` search, ordered by `UserRow.id`; `user_count()` counts the same set. `service.users_page()` then computes each row's sources (administrator check, observed rule match, exception lookup, team sources) concurrently, at most eight at a time. Individual exceptions are rows of `platform_access_users`, keyed by `user_id` (primary key, foreign key to `users.id`). `users` already carries the functional index `ix_users_lower_username` on `lower(username)`.

The rule tester reads the current administrator's row through the same query (`query` = their username, `limit` 100) to name their access sources.

The team "Add members" dialog (`AddTeamMembersDialog`) is a hand-rolled modal: an `Autocomplete` search that opens from two characters, a bordered "pending" list, Cancel and Confirm. It owns team-specific logic (role chips, add then grant calls).

## Goals / Non-Goals

**Goals:**

- The default page of the Users tab costs no more than today's page: one page query, one count, the unchanged per-row source computation for at most 25 rows.
- Both "add people" dialogs share one layout, so they cannot drift apart.

**Non-Goals:**

- No Alembic migration and no new index.
- No filter on "admitted by any source": rule, team and administrator sources are computed per user after the page is read.
- No bulk removal, no change to the per-row source computation, no change to the public access pages.

## Decisions

- **Parameter `exceptions_only: bool = False`.** The endpoint's parameters are bare lower-case words (`offset`, `limit`, `query`) and the store already names its one boolean narrowing `eligible_only` (`teams()`); "exception" is the word the code and the spec use for a `PlatformAccessUserRow`. Alternative: `source=individual`. Rejected: it suggests the other sources can be filtered, which is the out-of-scope case.
- **Filter as `EXISTS` on `platform_access_users.user_id`,** shared by the page query and the count so `total` always describes the same set. It is a primary-key probe. Alternative: an inner join; equivalent here, but `EXISTS` leaves the selected entity and the existing search predicate untouched.
- **Order: `lower(username) ASC NULLS LAST, id ASC`, in SQL, in both modes.** Users without a username sort after all named users, in id order. `NULLS LAST` is written explicitly because PostgreSQL and SQLite disagree on the default. An empty-string username is not null and sorts first; identities are created from the identity provider's username, so this is not expected in practice. Sorting on `lower(username)` only (not on the displayed fallback to email) keeps the expression identical to the existing functional index.
- **No migration.** In the unfiltered mode PostgreSQL can walk `ix_users_lower_username` in order. In the filtered mode the exception set is sorted in memory; it is bounded by the number of exceptions (at worst the initial import of every existing user, a few thousand rows of one text column). An index cannot serve the substring search in either mode, as before.
- **The per-row source computation is untouched,** including its own exception lookup. Returning the exception rows from the filtered query would save 25 primary-key reads per page but means a second code path for the same projection; left as a follow-up.
- **Shared shell `AddPeopleDialog`.** The markup and stylesheet of `AddTeamMembersDialog` move into a generic shared organism (title, subtitle, search, pending list with an optional per-row slot, actions). `AddTeamMembersDialog` keeps its props, its strings and its team logic and renders the shell with its role chips in the slot; the whitelist dialog renders the same shell without a slot. Alternatives: reuse `AddTeamMembersDialog` as is (impossible: it takes a team and performs team mutations); copy its layout into the page folder (rejected: two stylesheets to keep alike by hand).
- **`Autocomplete` gains an optional `noOptionsMessage`,** forwarded to `Menu`, which already has it. Without it the menu can only say the hard-coded "Aucune option disponible", so the whitelist search could not tell "searching" from "no match". Default unchanged.
- **The dialog searches one server page.** A query of two characters or more, debounced 300 ms, asks for the first 25 matches of all known users (filter off). When more match, a last non-selectable line says how many others there are and asks to refine the search. The pending list holds the selection across searches. People already holding an individual exception appear disabled with a second line saying so; people already in the pending list are left out of the suggestions, as in the team dialog.
- **The page drops row selection and the bulk bar.** The single-row "Allow" action goes too: every listed row holds an exception, so the only row action is "Remove". The single-grant endpoint and its hook stay (other callers may use them; removing an endpoint is not this change).
- **Empty whitelist vs. no match** is decided by whether a search is active when `total` is 0. The search field stays visible in both cases.
- **After a grant or a removal** the list refreshes through the existing cache invalidation of the users query. Removing the last row of a page other than the first leaves an empty page; the page then steps back to the previous one.

## Risks / Trade-offs

- [The default order changes for any other consumer of the endpoint] → the only consumers are this page and the rule tester, which looks a row up by id; stated in the contract entry and the migration note.
- [`AddTeamMembersDialog` is restructured] → its public props and its test file are unchanged, and its tests are run as part of this change.
- [The dialog has no pages, so a broad search shows only its first 25 matches] → the remaining count is shown with a prompt to refine; see the open question.

## Open Questions

- For the PR reviewer: the add dialog follows the team dialog's search-and-pending-list pattern, so results are not browsable page by page. If browsing all users page by page inside the dialog is wanted, it needs a table-in-dialog design (and a per-row "not selectable" state the shared `DataTable` does not have). Is the shared pattern acceptable?
- For the PR reviewer: the confirmation toast reports the number of people selected, not the number newly granted, because the bulk grant answers 204 without a count. Worth returning the count?
