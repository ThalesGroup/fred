## 1. Configured identity reads

- [x] 1.1 Add a request-scoped platform-access directory adapter for local and Keycloak search, ID lookup, and paged population reads; verify focused tests cover both modes, unavailable Keycloak, missing IDs, and multiple pages.
- [x] 1.2 Use current directory profiles to render and search SQL exceptions while retaining orphan exception IDs; verify paging, counts, provenance, profile refresh, and query tests.

## 2. Exception mutations

- [x] 2.1 Validate all selected identities against the configured directory and materialize missing Fred reference rows atomically before bulk grant; verify a Keycloak-only identity, duplicate IDs, and a late unknown ID with no partial grant.
- [x] 2.2 Apply the same directory validation to one-person grants and preserve revocation of an unresolved existing exception; verify route and service tests.

## 3. Initial import and review

- [x] 3.1 Enumerate the configured human directory for T0 preview and commit, evaluate only verified observations, and preserve the one-time SQL lock; verify federated-known, manually created, local, missing-evidence, multi-page, and concurrent cases.
- [x] 3.2 Use the same configured population for activation review without writing admission changes; verify counts and outcomes for directory-only and Fred-only identities.

## 4. Client and documentation

- [x] 4.1 Adapt the whitelist table and add dialog to current directory identities and unresolved IDs; verify targeted frontend tests for labels, search, unavailable directory, and existing grants.
- [x] 4.2 Regenerate API/client artifacts if contracts changed and reconcile the platform-access contract, UX doc, and operator note; verify generation diffs and `openspec validate --strict`.

## 5. Verification and close-out

- [x] 5.1 Run targeted checks, root `make code-quality`, relevant offline tests, a read-only local Keycloak smoke check, and local-directory focused tests; record actual results in this task or the PR.
- [ ] 5.2 Review the full branch against its target, obtain an independent read-only review, reconcile findings and specs, sync and archive the change, and verify the draft PR describes the final behavior.

Verification: 52 focused backend tests passed (10 PostgreSQL tests skipped without an isolated database); 85 focused frontend tests passed; targeted basedpyright passed; root `make code-quality` passed with ignored generated `target/company-jwt-provisioning` temporarily moved and restored. A read-only local Keycloak check verified paged search and UUID lookup. The independent branch reviewer found and rechecked bounded search, completed-import reads, mode-switch reference rows, exact-identity lookup, and operator guidance; all actionable findings were corrected.
