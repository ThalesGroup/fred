## Decisions

**Derive document readability from tags.** `document#read = read from parent` and `resource#read = read from parent`, so the set of readable documents equals the documents whose stored `tag_ids` intersect the readable tags. Authorizing tags (hundreds) instead of documents (unbounded) removes the dependence on corpus size without a per-document `Check`.

The rule relies on stored tag membership matching the FGA `parent` tuples, the same invariant folder inventories already use. If a tag write reached SQL but not OpenFGA, the document becomes visible to readers of a tag an editor deliberately placed it in: that is the intended state, not an escalation. The reverse drift (stale FGA tuple) only hides a document.

**Plain `ListObjects`, with a warning, for what still enumerates.** The remaining enumerations list one user's folders, teams and file areas: hundreds, not thousands. OpenFGA cuts any response at `listObjectsMaxResults` (1,000 by default) and at `listObjectsDeadline` (3 s by default), with no signal. The engine logs `outcome=possibly_truncated` when a response reaches 1,000 objects or takes 2.5 s. Each subfolder counts, so a user reading more than 1,000 folders in total would still be truncated, now visibly.

The streamed variant was rejected: it ignores the result limit, but the Python SDK logs and swallows connection and read errors, drops error frames and skips retries. An outage would then read as "no access" instead of failing.

**Label queries narrow by tags in SQL.** Passing every readable document uid as an expanded `IN` list would exceed the PostgreSQL bind-parameter limit on large corpora. A subquery on `tag_ids && :tags` keeps one array parameter.

## Deferred

- Failing explicitly, rather than warning, when a folder or team enumeration reaches the server limit. It needs a `rebac` setting mirroring `OPENFGA_LIST_OBJECTS_MAX_RESULTS`, hence a chart change.
- Tabular resolution loads the metadata of every document in the scope's folders, then keeps tabular ones in Python. Filtering on the tabular artifact in SQL would bound it to tabular documents.
- Folder item listings still check READ per document. The folder rule above would allow one folder check instead.
- Unscoped tabular listing (no team, personal or library scope) loads metadata for every readable document. Agent tools always carry a scope; only direct API calls without one pay this.
- Orphaned memberships from before the folder-inventory fix still need a repair pass.
