## 1. Restore compatibility within the security boundary

- [x] 1.1 Add failing real-parser regressions for reported `TRIM`/`SUBSTRING` expressions, both syntaxes, nesting and safe schema qualification; verify the current validator reproduces rejection.
- [x] 1.2 Derive schema-aware trusted built-in identities and apply them to expression and macro validation; verify the positive regressions and existing analytical-function tests pass.
- [x] 1.3 Exercise direct/nested inspection functions, unsafe macros, side effects, explicit catalogs, unknown schemas/functions, unauthorized relations and external table functions; verify each remains rejected.

## 2. Verify execution and close out

- [x] 2.1 Run the reported expression through the real tabular service with a synthetic local Parquet file and restricted DuckDB settings; verify expected rows and unchanged execution limits.
- [x] 2.2 Run the affected tabular suites and root quality check, then obtain independent author/security/performance review; record base/head, findings and dispositions in this task response.
- [x] 2.3 After coordinating the local Knowledge Flow API restart, repeat David test 2's audit in a fresh conversation and distinguish SQL recovery from semantic accuracy using the existing Small/Large evidence.
- [x] 2.4 Reconcile the shared `tabular-query-safety` capability with its existing pending change, sync/archive only the completed approved correction and verify strict OpenSpec validation. Keep all GitHub writes disabled.

Scope approved by the developer on 2026-10-29. Initial regression run: 12 failed and 34 passed; after the validator correction: 46 passed.

Verification: the final parser suite includes 47 cases (including a real pure macro with a qualified dependency). The 8073-row service regression finds the final row, respects a two-row result cap, and retains external-source and inspection rejection. Full Knowledge Flow offline suite: 1679 passed, 2 skipped, 47 integration tests deselected; 45 warnings, including dependency and background-thread cleanup warnings. Root `make code-quality` passes all modules. Tests invoking the real service needed execution outside the process sandbox; pytest disabled network sockets.

Independent read-only review covered base `33a727e07a39087696b5afb250321c3c7aee4584`, frontend HEAD `ddf0d39e0`, and the uncommitted SQL correction/tests/artifacts. It challenged actual DuckDB metadata, macro dependencies, qualified and nested inspection, relation authorization, MCP parsing, alias hiding, worker offload, metrics and multi-pod cache semantics. No actionable findings. No separate throughput or multi-pod campaign was required or claimed; scheduling, limits and shared state are unchanged.

Live validation after restarting only the local Knowledge Flow API with its original configuration:

- Direct authenticated HTTP queries on the existing g5 dataset return 200 for nested `LOWER(TRIM(...))`, SQL-standard `SUBSTRING` and `main.trim`, with the requested two-row cap. Inspection and unknown-schema expressions return 400.
- Six fresh David test 2 conversations used the real managed instance, its resources, the Large 4 chat profile and reasoning enabled. Each completed six tools without an error. Expected/returned anomaly counts are g1 10/10, g2 9/9, g3 9/10, g4 8/10, g5 9/9 and g6 5/5. Comparison uses (row ID, column, rule), because some campaign value/action text contradicts the actual rules. No expected anomaly is missing. Additional g3 REG-010 and g4 REG-016 alerts reflect rule overlap/undefined sums when monthly amounts are invalid; these are interpretation differences, not demonstrated SQL failures.
- Large sessions: g1 `239a6d33-9e9a-4f7f-b8a3-f966b4e8a87e`, g2 `45d6a15e-88f5-4791-8208-0c1498f8eab5`, g3 `31a9caed-c97a-4837-9a61-f216db42f1bd`, g4 `00598756-609d-4c8d-b6b6-cbea1029a2cc`, g5 `0c318703-eb2c-44dd-b39b-f639ca9b14f4`, g6 `0397ef19-a530-4657-9880-81e3e9b6d9b5`.
- Small g5 session `5e9107f2-f628-440f-9403-212c8bc6df32` still generates incompatible SQL syntax/types and reverses business rules (20 false alerts); the corrected restricted-built-in refusal is absent. The patch does not make Small a reliable auditor. Two initial CLI attempts without UI-equivalent reasoning/profile preparation returned out-of-scope answers with zero tools and are excluded from SQL acceptance evidence.
- Chrome verification on the completed g5 conversation confirms a successful rich structure panel, columns/types and hidden internal query alias. Frontend suites previously passed 4841 tests (8 skipped), with the final focused suites passing 226 tests.
- Latest attachment groups g7/g8 are not bound to this managed instance and were not audited end to end. The synthetic 8073-row service regression verifies full SQL filtering, not LLM context coverage.

Close-out: the main `tabular-query-safety` spec preserves the two shipped security requirements from the pending remediation delta and includes this correction's compatibility requirement. The unrelated pending change is left active and unmodified. The selected change and main capability pass strict validation; all 38 main specs pass ordinary validation. Global strict validation reports one pre-existing placeholder Purpose in `frontend-surface-scale`, which this patch does not modify. All work remains local; no GitHub write or detailed Jira analysis note was published.
