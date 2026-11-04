## 1. Trusted failure feedback

- [ ] 1.1 Replace empty caught-MCP error artifacts with bounded Fred-owned diagnosis/recovery messages in `context_aware_tool.py`; verify recognized HTTP envelopes, direct HTTP errors and unknown exceptions through the real resolver, including the pre-invocation inventory 401.
- [ ] 1.2 Add a defensive non-empty renderer fallback while preserving curated SQL 400 detail and run-stop/cancellation propagation; verify empty/whitespace blocks, malicious provider text, signed URLs, delegated refusal and cancellation regressions.

## 2. Contextual trace details

- [ ] 2.1 Extend `traceUtils.ts` and `TraceDetailDrawer` to show recorded per-tool business arguments and the safe recorded error, preserving the attempted-SQL view; verify French/English rendering, invalid submitted identifiers and no-argument calls, with no next-step section or recovery advice and no exposed credentials/injected scope internals.
- [ ] 2.2 Verify identical failed-call detail after live SSE handling and history reload, including a partially failed tool batch; use focused hook/drawer tests and a manual light/dark-theme check without adding a toast per failed call.

## 3. Concise tool guidance

- [ ] 3.1 Clarify `document_uids`, `dataset_uids` and `sql` descriptions in Knowledge Flow; verify the published tool/OpenAPI descriptions and unchanged field names, opaque UID compatibility and authorization behavior, then regenerate the existing OpenAPI/frontend client artifacts.
- [ ] 3.2 Amend packaged tabular instructions with type-aware DuckDB date arithmetic and exact categorical-text filtering; verify at most one date expression example, a net increase of at most 100 English words, and DuckDB checks for typed DATE/TIMESTAMP, timestamp-shaped text and the unsupported SQLite signature.

## 4. Verification and delivery

- [ ] 4.1 Update the existing runtime contract and trace UX guidance, add one English migration note with impact `none`, and verify their statements against the implemented behavior and #3458.
- [ ] 4.2 Run focused runtime, Knowledge Flow, capability and frontend suites plus required root quality checks and applicable type/generated-client checks; record commands, results and any exclusions in the existing PR/tasks.
- [ ] 4.3 Apply `audit-branch` against the actual target base and obtain an independent read-only review of failure confidentiality, affected consumers and bounded work; record base/head, findings and dispositions before declaring readiness.
- [ ] 4.4 Push the reviewed topic branch and open a draft PR titled with #3458, reconcile the artifacts with final behavior, sync specs and archive this change following the repository procedures; verify the PR attachment and CLI archive result.
