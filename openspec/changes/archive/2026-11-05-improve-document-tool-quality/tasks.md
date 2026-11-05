## 1. Establish the baseline

- [x] 1.1 Add focused regressions for provider-visible UID parameter guidance, NUL write rejection and durable diagnostic history; run them on swift and record the failing boundaries.
- [x] 1.2 Inspect available captured model contexts for the failed document references and replay representative real-model requests where configuration permits; retain redacted before/after outcomes.

## 2. Implement document-tool reliability

- [x] 2.1 Add shared exact-reference parameter descriptions and concise tool-role guidance without changing fields, lookup behavior or scope; verify provider schemas and existing reading/summary tests.
- [x] 2.2 Reject NUL title/content before document-store access with a non-empty error artifact; verify create/update preservation, open-document reuse and valid Unicode.
- [x] 2.3 Normalize NUL values only in history persistence copies with explicit attribution; verify nested values, IDs, status, input immutability and separate-reader round trips, including actual PostgreSQL when available.

## 3. Validate and close out

- [x] 3.1 Run relevant offline suites and root code-quality, assess serialization cost, and record actual audit replay outcomes with limits in these tasks and the task response.
- [x] 3.2 Complete full-branch author review and independent correctness/performance review against origin/swift; disposition findings and verify affected corrections.
- [x] 3.3 Add the migration note and compact contract guidance, reconcile/sync/archive the completed OpenSpec change, and commit the dedicated branch for #3477 without opening a PR, as requested.

Evidence: base d9eb3738f83bb73cdcf5ba5c14ba602a94e6beea. Baseline regressions showed absent parameter descriptions, invalid text reaching storage (four cases), and unnormalized historical text. Updated document suites passed 80 tests; writable suites passed 77. The generated provider schema now contains the shared parameter guidance.

Captured contexts were inspected locally: the corrupt-UID read had five discovered UID values available; a representative failed summary had loaded its skill but had no discovered UID. No captured content was exported. Automatic approval review rejected the external replay, and the developer explicitly chose to continue without sending captures on 2026-11-05. Real-model improvement and authenticated UI replay remain unverified; schema/port tests do not establish that the 11 model-reference mistakes disappear.

PostgreSQL evidence: the exact captured observation 21f8d2ccf6bb6c94 (107 NUL) reproduced DBAPIError in both the swift document write and JSONB history save. Corrected code rejected the document with a non-empty result, retained all four history rows with paired IDs and 107 attributed replacements, preserved live input, and accepted corrected Markdown. All disposable schemas were removed. One permanent PostgreSQL integration test passed.

Verification: root Make test with the four affected modules passed 1298 core, 80 documents, 77 writable and 64 access tests (1519 total); runtime history/read consumers passed 63 tests. The final writable test-only correction passed all 10 tests in its file. Raw core typing has zero errors and two pre-existing unreachable-code warnings; raw writable typing has 16 pre-existing baseline diagnostics in unchanged test code and no new diagnostics.

Root code-quality passed every configured module across two root invocations: the first passed all Python libraries/capabilities, then stopped at the frontend Node version guard; the second resumed the remaining frontend/application modules using installed Node 24 and passed. The final summary guidance delta passed the 80 document tests plus Ruff lint/format checks. Root migration-check passed with one new declaration. The main specification was synchronized, validated strictly, and the complete 40-spec validation passed before archiving.

Independent review: base d9eb3738f83bb73cdcf5ba5c14ba602a94e6beea, implementation head 80eb2ae37250d952c2ac61ff517da05235ed5352 plus the reviewed ainvoke test correction. Full branch, consumers, docs, authorization preservation, failure rendering, history serialization, async/client/KPI and multi-pod ownership reviewed with audit-branch and fred-performance-reviewer. One P2 (three new test type errors) was fixed and its delta re-reviewed; no remaining actionable findings. No model export, authenticated UI, multi-pod deployment or load campaign was performed.

Follow-up review covered the typed invocation correction at dac9a2a045c5ad29403af6c19ce712a613612bac and the final summary/tree guidance delta committed as 22d49fffc. Both were accepted without further findings. The summary guidance now names the actual tree records' uid and folder_id fields. OpenSpec close-out only changes specification placement and verification evidence; it adds no runtime behavior.

Cost check: 200 local normalization samples per size; p95 was 0.020 ms for 5k characters, 0.097 ms for 100k, and 0.697 ms for 1M normal-text characters. This measures the added local pass only, not end-to-end latency or concurrent-load capacity.
