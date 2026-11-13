## 1. Progressive SQL result inspection

- [x] 1.1 Developer follow-up explicitly requests implementation and legacy token-code removal; the old unimplemented proposal is removed. Retain the cancelled token-counting decision in #3527/#3528.
- [x] 1.2 Add an explicit preview-row limit while retaining the helper's existing default for other consumers; verify SQL initially shows ten rows with all columns and tabular search retains its current bounds.
- [x] 1.3 Add the small French/English reveal action and call-scoped expansion state; verify 10/20/25 progression, actual remainder labels, no action for zero-to-ten rows, and disappearance when exhausted.
- [x] 1.4 Verify switching between calls with identical SQL, closing/reopening, and unrelated live updates reset or preserve expansion as specified; retain complete SQL/response copying, original colors, safe failures, unknown-tool redaction and tool-owned truncation notices using the existing renderer/interactions.
- [x] 1.5 Remove the unused model-call attribution fields, helper and runtime/history/SSE propagation; regenerate runtime OpenAPI/client and verify legacy history remains readable, attribution is not newly emitted, and established token_usage/context_tokens accounting tests pass.

## 2. Verification and close-out

- [ ] 2.1 Manually inspect desktop and narrow-width presentation with the existing UI, then run affected frontend suites and root make code-quality; record any unavailable browser coverage explicitly in the PR.
- [ ] 2.2 Apply the branch audit and obtain an independent read-only correctness/performance review of the implementation; disposition findings and record reviewed scope, base/head, verification and exclusions in #3528.
- [ ] 2.3 Reconcile the runtime contract, COMPONENT-UX.md and the existing migration note, validate the completed change and current specs, then sync/archive through the repository procedure after implementation is verified.

Verification: 447 frontend tests across eight suites and 73 runtime tests passed. Independent review against 644ea4bdf found an empty-final history accounting regression; explicit non-None guards and four independently passing history regressions resolved it. The review covers this change and affected consumers, with earlier committed #3527/#3537 work excluded except existing recorded review evidence. Runtime codegen ran through `make -C apps/frontend update-runtime-api`; no production attribution references remain. Browser validation: Chrome control fails internally; the integrated browser works but requires a separate login, requested from the developer. Root quality and browser outcome are pending.
