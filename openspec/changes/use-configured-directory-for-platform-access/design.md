## Context

See proposal.md. `platform_access_users.user_id` has a foreign key to `users.id`; the latter also stores verified admission evidence and unrelated Fred state. Platform-access user pages and T0 currently iterate `UserRow`. Team candidate search and member display instead use `users.service`, which selects Keycloak or the local store from `security.user_directory`. The browser uses `GET /admin/platform/access/users` for both the exception table and the add dialog. A completed T0 is immutable.

## Goals / Non-Goals

**Goals:** Preserve the SQL admission authority and its audit and concurrency guarantees; use one configured identity authority for all platform-access user selection and display; keep existing exception IDs actionable when their directory profile disappears; avoid evaluating admission rules from unverified Keycloak profile data.

**Non-Goals:** Create Keycloak users, import the whole upstream Active Directory, merge Keycloak and local directories within one deployment, or automatically rerun a completed T0.

## Decisions

1. **Use a control-plane directory adapter.** Platform-access routes receive request-scoped user-service dependencies, like team routes. The adapter exposes paged search, lookup by IDs, and one paged population enumeration. `local` reads `UserRow`; `keycloak` uses the Keycloak admin API. It never falls back across modes. An unavailable provider yields an availability error; an individual 404 is represented as an unresolved identity. Keep the SQL store unaware of Keycloak.

2. **Page exceptions in SQL, then hydrate identities.** Without a search, select one SQL exception page and resolve its IDs in a bounded Keycloak batch. With a search, obtain the directory's matching IDs in pages and intersect them with SQL exceptions before SQL pagination and count. This prevents stale Fred names from controlling search, keeps the exception list's count accurate, and retains unresolvable exception IDs on an unfiltered page. For the add dialog, search the configured directory and annotate returned IDs with their current exception state. Avoid one Keycloak request per displayed row when a directory scan or batch lookup is cheaper, following `users.service.get_users_by_ids`.

3. **Materialize a minimal Fred row when granting a new Keycloak identity.** Validate every selected ID against the configured directory before beginning SQL mutation. Within the SQL transaction, create any missing `UserRow` with the directory's profile solely to satisfy the existing foreign key, then add missing exceptions. Keep already observed admission claims and later token observations intact. Directory validation failure, an unknown identity, or a later batch error aborts the whole grant. Do not change the FK or add a second user table.

4. **T0 uses one directory enumeration before its SQL commit.** Fetch a complete, paged human-identity snapshot from the configured directory; exclude known service accounts. Use existing fresh, unconflicted verified claim observations in Fred to classify matches. Unknown evidence is a T0 candidate. Under the existing policy lock and revision check, create minimal rows for newly imported directory IDs and their exceptions, then mark completion in the same SQL transaction. The preview and activation review use the same directory enumeration and classification rules. The provider enumeration is not a distributed snapshot of a changing Keycloak realm; the fixed population is the successful enumeration used for the commit.

5. **Resolve display names by stable ID.** Current directory profiles override local profile columns in responses; the admission sources and grant metadata still come from SQL. A missing directory identity displays its stable ID and exception origin, never three empty cells. If Keycloak is unavailable, return an error instead of turning all rows into orphans. The frontend can keep its table and add-dialog controls; adjust the identifier fallback and any loading/error copy as needed.

## Risks / Trade-offs

- **Broad directory searches and T0 scans can be expensive** - use server paging and bounded concurrent lookups, and test a population larger than one page. Do not run a full directory scan for each unfiltered exception page.
- **Keycloak changes during T0 enumeration** - check the SQL policy revision before commit and document that the imported cohort is the enumerated directory result, not a transaction across Keycloak and PostgreSQL.
- **Existing completed imports and missing identities** - do not reimport automatically or restore deliberate removals. Show unresolved exception IDs; provide an operator check for identifying current Keycloak IDs and manually grant any missing users.
- **Directory failure during grant or preview** - fail the operation without partial SQL changes and keep the last saved policy unchanged.

## Migration Plan

No schema migration. Deploy all readers with the new directory-backed API behavior. Existing exception IDs remain valid and resolve to current profiles when available. An operator on a completed T0 compares the existing exception IDs with the selected directory and uses normal manual grants for omissions; a normal upgrade does not reset `t0_completed_at`.
