## Decisions

- **Email as the identifier.** Normalized with `strip().lower()`, unique. Matched against the principal's configured email claim. When the token carries `email_verified: false`, no match is made, so a self-declared address cannot claim an entry.
- **Conversion, not a second admission path.** A pending entry becomes an ordinary `platform_access_users` row (source `manual`, original `granted_by`/`granted_at`), then is deleted, in one transaction under the existing policy lock. Listing, removal, actor safeguards and team sources stay unchanged.
- **Only on refusal.** The lookup runs in `admitted()` after `eligible()` returns false, so requests from already admitted people do not touch the new table.
- **Known identities stay on the existing path.** Adding an email that matches an existing directory identity (Keycloak search, or a Fred `users` row with that email) is refused with `409 platform_access_email_known` and the UI tells the admin to pick the person instead, so one person never has two entries.

## Deferred

- Bulk paste of many emails, expiry of pending entries.

## Cleanup filter and bulk removal

- **Filter is server-side**, because the table is paginated. When `overlap` is set, the service loads every individual exception once and computes, per person: rule match from the last stored verified evidence, ignoring its expiry (admission requires unexpired evidence, but the question here is who the rule covers, not who is signed in), team sources from one `lookup_subjects` call per authorized or Free team (not one check per person), and admin. Then it filters, counts and paginates. Without `overlap`, the current path is unchanged.
- **"Whitelist only"** means no source other than the individual exception: no rule, team, Free or admin source.
- **Select all across pages** is sent as a query (`all_matching` + `query` + `overlap` + `excluded_ids`), not as a list of ids, so the server resolves the exact set at request time; the deletion then runs in one transaction. The UI shows "N selected" from the filtered `total` minus the excluded ids.
- **Atomic and guarded.** The removal runs in one transaction under the policy lock. If filtering is active and the acting administrator would lose their last source, the whole call is refused with the existing error.
- **Unknown rule evidence.** Only the claim paths of the saved rule are stored per person. A person whose stored evidence lacks a path the current rule uses (rule widened to a new claim, or no sign-in since import) is "unknown": listed under neither of the other two chips, and listed by its own "To check" chip (`overlap=unknown`). A notice with a count was tried first; the owner dropped it because it shifted the layout. Evidence fills in on their next request.
- **Header select-all** needed one generic DataTable prop, `headerSelection`, overriding the page-scoped header checkbox. Rows still report their own state through `onSelectionChange`.
- **French chip label** is "Liste blanche seule", matching the page's existing "liste blanche" wording.
- **No refresh button.** The owner dropped it after trying it: reloading the page refetches the listing.
- **Toolbar:** "Add" then a "more" menu holding the initial import or reimport on the left; the overlap chips then a half-width search on the right, right above the table.
- **Chip counts** come from `GET /admin/platform/access/users/overlap-counts`, requested once per search; the listing stays paginated. The "All" chip has no count (FilterChips offers none); the pagination shows the total.
- **Active chip** uses primary-container / on-primary-container in the shared FilterChips (owner's choice after trying secondary-container); this changes all five FilterChips screens.
