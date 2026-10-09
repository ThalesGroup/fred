## 1. Server filtering and cleanup

- [ ] 1.1 Add status filtering and team-wide inactive count to invitation list schemas/service/routes, preserving lifecycle priority and one UTC evaluation instant; verify filtered totals, page boundaries, suspended behavior and revoked/expired overlap in `test_platform_access.py`.
- [ ] 1.2 Add the administrator-only inactive cleanup endpoint and atomic team-scoped deletion under the existing mutation transaction, returning/auditing deleted count; verify cross-team isolation, expiry boundary, preservation of usable links and membership, idempotency, rollback and unauthorized refusal in targeted backend tests.
- [ ] 1.3 Regenerate the control-plane client with `make update-control-plane-api` and wire generated hooks plus scoped RTK invalidation; verify generated request/response types include the status, inactive count and cleanup response without hand-written API types.

## 2. Invitation history controls

- [ ] 2.1 Add localized All/Active/Revoked/Expired/Suspended selection using Fred Select, resetting paging and hiding stale results; verify the query arguments and first-page transition in `PlatformAccessLinkManager.test.tsx`.
- [ ] 2.2 Add the shared destructive button/confirmation Dialog and actual-count success feedback, preserving filter on refresh and guarding busy/error states; verify cancellation issues no mutation, confirmation deletes for the selected team, failures retain history and success refreshes counts/pages in targeted frontend tests.
- [ ] 2.3 Check the local UI with existing test-team links and capture filter/confirmation states; verify no layout overflow and that Create link/Copy URL flows remain usable. Keep captures local and uncommitted.

## 3. Review and close-out

- [ ] 3.1 Update the existing UX, product-contract and migration documentation for confirmed permanent history cleanup; verify no obsolete timestamp/counter wording and no migration added.
- [ ] 3.2 Run root `make code-quality` once for the completed series and the relevant targeted tests, then perform author and independent read-only review; record tested head, coverage, findings and dispositions in the existing PR.
- [ ] 3.3 Commit server behavior and frontend controls as distinct logical blocks, push to PR #2966 and answer actionable quality-bot comments in English; verify the remote head and review threads, reconcile tasks/specs and archive the completed change.
