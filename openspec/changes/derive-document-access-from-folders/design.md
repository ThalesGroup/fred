## Decisions

**Folders select candidates; OpenFGA authorizes objects.** Stored `tag_ids` can disagree with OpenFGA parents after a completed folder removal races a stale title, name, retrievability or resource-content save. The lost update predates this PR; treating its SQL result as a grant newly exposes denied metadata, labels, resources and tabular content. Existing stale rows must remain confidential without repair.

Reuse candidate `has_user_permission` checks, in batches of at most 10, before returning metadata, labels, resources or tabular datasets. Deduplicate document IDs; propagate authorization errors. Keep the existing service-agent team-scoped exception (only without delegation caller role), disabled ReBAC and uploader-only tagless attachments. No model, API or architecture change is needed.

Ordinary metadata listing and resource listing cost one folder ListObjects plus one Check per unique candidate. Label search/pages cost one folder lookup plus M Checks for M matching UIDs on every request; authorize before sorting/counting/slicing, then hydrate only the page. Vocabulary checks C folder candidates and uses their already hydrated labels. Tabular checks each unique tabular candidate once, preserving scope. The 10-call bound is per request, not a global limiter; 200 concurrent requests can still demand up to 2,000 Checks. No SQL transaction or connection is held across these calls. This is correctness evidence, not a load-capacity claim.

Full metadata/resource writes remain a pre-existing lost-update risk, including ingestion's complete updates and parent reassertion. This correction protects reads when SQL is stale and OpenFGA denies; it does not repair data or change write ownership. Extending it into concurrency control for all mutations would be a separate scoped change.

**Plain `ListObjects`, with a warning, for what still enumerates.** The remaining enumerations list one user's folders, teams and file areas: hundreds, not thousands. OpenFGA cuts any response at `listObjectsMaxResults` (1,000 by default) and at `listObjectsDeadline` (3 s by default), with no signal. The engine logs `outcome=possibly_truncated` when a response reaches 1,000 objects or takes 2.5 s. Each subfolder counts, so a user reading more than 1,000 folders in total would still be truncated, now visibly.

The streamed variant was rejected: it ignores the result limit, but the Python SDK logs and swallows connection and read errors, drops error frames and skips retries. An outage would then read as "no access" instead of failing.

**Label candidates narrow by tags in SQL.** A subquery on `tag_ids && :tags` keeps one array parameter. Candidate authorization is followed by in-memory UID pagination; metadata hydration uses existing 2,000-UID SQL chunks. Vocabulary uses hydrated labels rather than an unbounded UID bind list. Disabled ReBAC retains store-side pagination and distinct-label queries.

## Deferred

- Failing explicitly, rather than warning, when a folder or team enumeration reaches the server limit. It needs a `rebac` setting mirroring `OPENFGA_LIST_OBJECTS_MAX_RESULTS`, hence a chart change.
- Tabular resolution loads the metadata of every document in the scope's folders, then keeps tabular ones in Python. Filtering on the tabular artifact in SQL would bound it to tabular documents.
- Unscoped tabular listing (no team, personal or library scope) loads metadata for every readable document. Agent tools always carry a scope; only direct API calls without one pay this.
- Orphaned memberships from before the folder-inventory fix still need a repair pass.
