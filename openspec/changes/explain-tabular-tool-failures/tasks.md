## 1. Trusted failure feedback

- [x] 1.1 Replace empty caught-MCP error artifacts with bounded Fred-owned diagnosis/recovery messages in `context_aware_tool.py`; verify recognized HTTP envelopes, direct HTTP errors and unknown exceptions through the real resolver, including the pre-invocation inventory 401.
- [x] 1.2 Add a defensive non-empty renderer fallback while preserving curated SQL 400 detail and run-stop/cancellation propagation; verify empty/whitespace blocks, malicious provider text, signed URLs, delegated refusal and cancellation regressions.

## 2. Contextual trace details

- [x] 2.1 Extend the existing trace utilities and `TraceDetailDrawer` to show recorded per-tool business arguments and the safe recorded error, preserving the attempted-SQL view; verify French/English rendering, invalid submitted identifiers and no-argument calls, with no next-step section or recovery advice and no exposed credentials/injected scope internals.
- [x] 2.2 Verify identical failed-call detail after live SSE handling and history reload, including a partially failed tool batch; use focused hook/drawer tests, inspect reused theme tokens and attempt a manual light/dark-theme check (record any unavailable local UI) without adding a toast per failed call.

## 3. Concise tool guidance

- [x] 3.1 Clarify `document_uids`, `dataset_uids` and `sql` descriptions in Knowledge Flow; verify the published tool/OpenAPI descriptions and unchanged field names, opaque UID compatibility and authorization behavior, then regenerate the existing OpenAPI/frontend client artifacts.
- [x] 3.2 Rewrite the complete packaged tabular prompt for readable workflow and result handling, preserving existing discovery/schema/source/type rules; verify at most one date example, no word-count growth, and DuckDB checks for date arithmetic and exact-text filters.
- [x] 3.3 Add the explicit zero-row success message to structured SQL responses and localized chat details; verify empty success, populated success, zero/null aggregates and error paths, with no cache or duplicate-call enforcement.

## 4. Verification and delivery

- [x] 4.1 Update the existing runtime contract and trace UX guidance, add one English migration note with impact `none`, and verify their statements against the implemented behavior and #3458.
- [ ] 4.2 Run focused runtime, Knowledge Flow, capability and frontend suites plus required root quality checks and applicable type/generated-client checks; record commands, results and any exclusions in the existing PR/tasks.
- [ ] 4.3 Apply `audit-branch` against the actual target base and obtain an independent read-only review of failure confidentiality, affected consumers and bounded work; record base/head, findings and dispositions before declaring readiness.
- [ ] 4.4 Push the reviewed topic branch and open a draft PR titled with #3458, reconcile the artifacts with final behavior, sync specs and archive this change following the repository procedures; verify the PR attachment and CLI archive result.

## Verification evidence

- Runtime: 145 targeted tests passed (context injection, provider resolution,
  failure rendering, cancellation/authority and both HTTP client error types).
  After the final test typing correction, all 66 resolver tests passed again.
- Frontend: 332 focused tests passed; the final confidentiality regressions
  bring the drawer suite to 32 passing tests. Coverage includes actual SSE
  projection, a history JSON round trip, partial batches and French/English
  cause-only translations. Typecheck and OpenAPI regeneration passed.
- Knowledge Flow: 69 contract tests passed; wider offline suite completion is
  being finalized using the standard `not integration` marker.
- Manual DuckDB checks passed for typed date arithmetic, rejection of SQLite's
  date modifier and exact stored-string filtering. The installed MCP catalog
  loads the 531-word prompt (previously 796 words).
- Browser check attempted: localhost:5173 refused the connection. Manual
  light/dark validation is unavailable; reused error-container foreground and
  background tokens and wrapping rules were inspected. No visual check or
  model-campaign error-rate reduction is claimed.
- Independent review covered base 0773ff95d through 9859738a8 and local docs.
  The four original findings were corrected. The follow-up SQL category
  narrowing is committed at 9ba01df68; final disposition remains pending.
