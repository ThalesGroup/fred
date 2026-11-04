## 1. Trusted failure feedback

- [x] 1.1 Replace empty caught-MCP error artifacts with bounded Fred-owned diagnosis/recovery messages in `context_aware_tool.py`; verify recognized HTTP envelopes, direct HTTP errors and unknown exceptions through the real resolver, including the pre-invocation inventory 401.
- [x] 1.2 Add a defensive non-empty renderer fallback while preserving curated SQL 400 detail and run-stop/cancellation propagation; verify empty/whitespace blocks, malicious provider text, signed URLs, delegated refusal and cancellation regressions.

## 2. Contextual trace details

- [x] 2.1 Extend the existing trace utilities and `TraceDetailDrawer` to show recorded per-tool business arguments and the safe recorded error, preserving the attempted-SQL view; verify French/English rendering, invalid submitted identifiers and no-argument calls, with no next-step section or recovery advice and no exposed credentials/injected scope internals.
- [x] 2.2 Verify identical failed-call detail after live SSE handling and history reload, including a partially failed tool batch; use focused hook/drawer tests, inspect reused theme tokens and attempt a manual light/dark-theme check (record any unavailable local UI) without adding a toast per failed call.

## 3. Concise tool guidance

- [x] 3.1 Rewrite all four MCP tool descriptions and clarify `document_uids`, `dataset_uids`, `sql`, `keyword` and `max_rows` descriptions in Knowledge Flow; verify the published tool/OpenAPI descriptions and unchanged field names, opaque UID compatibility and authorization behavior, then regenerate the existing OpenAPI/frontend client artifacts.
- [x] 3.2 Rewrite the complete packaged tabular prompt for readable workflow and result handling, preserving existing discovery/schema/source/type rules; verify at most one date example, no word-count growth, and DuckDB checks for date arithmetic and exact-text filters.
- [x] 3.3 Add the explicit zero-row success message to structured SQL responses and localized chat details; verify empty success, populated success, zero/null aggregates and error paths, with no cache or duplicate-call enforcement.

## 4. Verification and delivery

- [x] 4.1 Update the existing runtime contract and trace UX guidance, add one English migration note with impact `none`, and verify their statements against the implemented behavior and #3458.
- [x] 4.2 Run focused runtime, Knowledge Flow, capability and frontend suites plus required root quality checks and applicable type/generated-client checks; record commands, results and any exclusions in the existing PR/tasks.
- [x] 4.3 Apply `audit-branch` against the actual target base and obtain an independent read-only review of failure confidentiality, affected consumers and bounded work; record base/head, findings and dispositions before declaring readiness.
- [x] 4.4 Push the reviewed topic branch, open and attach the draft PR titled with #3458, reconcile the artifacts with final behavior and sync both main specs. Archive the completed change as the standard close-out operation.

## Verification evidence

- Runtime: 145 targeted tests passed (context injection, provider resolution,
  failure rendering, cancellation/authority and both HTTP client error types).
  After the final test typing correction, all 66 resolver tests passed again.
- Frontend: 418 focused tests passed after rebase, including 32 drawer tests
  and the affected managed-chat/history consumers. Coverage includes actual SSE
  projection, a history JSON round trip, partial batches and French/English
  cause-only translations. Typecheck and OpenAPI regeneration passed.
- Knowledge Flow: 168 selected unit tests passed with two integration tests
  deselected by the standard `not integration` marker. The isolated integration
  HTTP-server test requires network access and was not counted as unit evidence.
- Manual DuckDB checks passed for typed date arithmetic, rejection of SQLite's
  date modifier and exact stored-string filtering. The installed MCP catalog
  loads the 531-word prompt (previously 796 words).
- Browser check attempted: localhost:5173 refused the connection. Manual
  light/dark validation is unavailable; reused error-container foreground and
  background tokens and wrapping rules were inspected. No visual check or
  model-campaign error-rate reduction is claimed.
- Independent full-branch review covered the original base and then the final
  corrective/rebase delta against origin/swift 059ae1c91 through 2ca0ce328.
  Four initial findings plus the SQL category-narrowing follow-up were fixed
  and independently closed. Coverage included MCP/resolver/rendering, SQL
  contracts/client/prompt, privacy, bounded work, live/history and incoming HITL
  compatibility. No supported residual findings. The subsequent spec sync only
  copies the already reviewed requirements. No shipped tabular Graph consumer
  was found; richer Graph drawer behavior and load tests were not established.
- Both modified main specs and the change pass strict OpenSpec validation.
  A broader spec scan reports a pre-existing placeholder Purpose in unchanged
  frontend-surface-scale; it is outside this change.

- Final description pass: all four controller summaries/docstrings and request
  metadata were rewritten and independently reviewed with no actionable
  mismatch (61717d119 plus the final local delta). Tool descriptions total
  444 words versus 462 before; redundant request examples were removed.
  Twenty-one published-MCP/controller tests passed; regenerated OpenAPI/client
  and the final narrow formatting checks passed.
- Root `make code-quality` completed successfully across all 17 modules, exit 0.
  Existing unreachable-code warnings remain in unrelated runtime files.
  After the TypeScript library-compatibility correction, typecheck and 233
  affected frontend tests passed. SDK MCP catalog/capability tests: 56 passed.
- Migration declaration validation passed against origin/swift. The final base
  is 059ae1c91; rebase preserved both HITL and tabular trace behavior. The sole
  rebase conflict was independent appended runtime-contract sections, both kept.

- Delivery: draft PR #3460 was created against swift and attached to the task.
  Both main specs were verified to contain every delta before archival.
- OpenSpec archival succeeded via CLI on 2026-11-04. Specs were already
  synchronized and verified; archive used --skip-specs to avoid a duplicate sync.
