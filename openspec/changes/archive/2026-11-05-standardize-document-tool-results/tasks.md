## 1. Complete the selected policies

- [x] 1.1 Project native vector-search references as document_uid and update affected guidance; verify text/JSON equality, absent legacy key, exact read/summary chaining and unchanged citation UID/scope.
- [x] 1.2 Strip NUL before writable title matching/storage and disclose counts in a successful result; verify create, update, deduplication, import, all-NUL fields and preservation of valid Unicode/markers.

## 2. Verify and close out

- [x] 2.1 Reproduce the exact 107-NUL audit write on actual disposable PostgreSQL with successful editor/document output and durable paired history, and replay the captured model write to verify no correction round is required.
- [x] 2.2 Run affected module/consumer suites and root code-quality/migration checks; record results and any exclusions in these tasks and #3477.
- [x] 2.3 Complete author review against origin/swift and independent correctness/performance review including the new delta; resolve findings and verify corrections.
- [x] 2.4 Reconcile the existing runtime/migration guidance, sync and archive the modified specification, commit/push the existing branch and update #3477 without creating a PR.

Scope confirmation: the developer explicitly requested both policies on 2026-11-05 after inspecting the before/after page and the implementation-status table. This follow-up supersedes the earlier naming preservation and NUL rejection choices; original archived evidence remains historical.


Verification and review (2026-11-05):

- Implementation: 6bc9345dd, based on origin/swift d9eb3738f83bb73cdcf5ba5c14ba602a94e6beea. Native search text/JSON expose only document_uid; an ad hoc public-tool chain preserved an opaque non-UUID reference through actual read/summary tools and retained typed citation uid.
- The three affected module suites passed 80 + 79 + 64 = 223 offline tests; affected runtime/history/scope consumers passed 63; two opt-in disposable-PostgreSQL integration cases passed. Root make code-quality and make migration-check passed. Sandbox thread/async callbacks stalled two tests; the same test and complete suites passed outside that sandbox with pytest's network guard retained. No product workaround was added.
- Exact audit input with 107 NUL and captured model input with 82 NUL both saved on first invocation in actual PostgreSQL. Stored/editor content matched cleaned input; four paired history rows per case retained success and attributed raw arguments. A separate actual mistral-small-latest continuation after the 82-NUL save finished with one successful write, one saved document and four history rows, without a correction call. All temporary schemas were removed. This is one continuation, not a repeat of the earlier eight full-session campaign or a statistical reliability estimate.
- Full-branch author review and fresh independent read-only correctness/performance review covered native projection, UID/scope adapters, writable/import/title matching/editor output, history pairing and representation, ReAct/Graph/UI consumers, docs, async client reuse and multi-pod behavior. Reviewed base d9eb3738f83bb73cdcf5ba5c14ba602a94e6beea to head 6cb10f768bfa243677d9965c95eccf37172dd711 plus the implementation working diff, committed without production changes as 6bc9345dd. No supported actionable findings; earlier public-tool invocation and test typing fixes remain present. Subsequent marker metadata and final spec/evidence-only deltas received author review.
- Exclusions: no authenticated browser UI, deployment or load campaign. Tree records, typed citations, backend search schemas, builtin knowledge.search and similarity-result output names intentionally retain their own uid contracts. Linear local text/projection work adds no I/O or shared coordination; existing actual scope enforcement tests remain green.
- The changed main spec and change pass strict validation. All 40 main specs pass normal validation; optional repository-wide strict validation reports one pre-existing unrelated frontend-surface-scale Purpose placeholder, confirmed unchanged in origin/swift. The follow-up main spec replaces both superseded rejection requirements; the earlier archive remains historical.
- Runtime contract and migration note describe the intentional minor native-result compatibility change and automatic removal. No database/configuration migration or corpus rewrite. Synchronized/archive evidence and issue #3477 accompany the pushed existing topic branch; no PR is created.
