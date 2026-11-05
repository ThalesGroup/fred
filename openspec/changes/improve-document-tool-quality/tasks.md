## 1. Establish the baseline

- [ ] 1.1 Add focused regressions for provider-visible UID parameter guidance, NUL write rejection and durable diagnostic history; run them on swift and record the failing boundaries.
- [ ] 1.2 Inspect available captured model contexts for the failed document references and replay representative real-model requests where configuration permits; retain redacted before/after outcomes.

## 2. Implement document-tool reliability

- [ ] 2.1 Add shared exact-reference parameter descriptions and concise tool-role guidance without changing fields, lookup behavior or scope; verify provider schemas and existing reading/summary tests.
- [ ] 2.2 Reject NUL title/content before document-store access with a non-empty error artifact; verify create/update preservation, open-document reuse and valid Unicode.
- [ ] 2.3 Normalize NUL values only in history persistence copies with explicit attribution; verify nested values, IDs, status, input immutability and separate-reader round trips, including actual PostgreSQL when available.

## 3. Validate and close out

- [ ] 3.1 Run relevant offline suites and root code-quality, assess serialization cost, and record actual audit replay outcomes with limits in these tasks and the task response.
- [ ] 3.2 Complete full-branch author review and independent correctness/performance review against origin/swift; disposition findings and verify affected corrections.
- [ ] 3.3 Add the migration note and compact contract guidance, reconcile/sync/archive the completed OpenSpec change, and commit the dedicated branch for #3477 without opening a PR, as requested.
