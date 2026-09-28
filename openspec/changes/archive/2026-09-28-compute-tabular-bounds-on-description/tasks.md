## 1. Description-time values

- [x] 1.1 Replace the old-metadata no-scan service test with a failing CSV and multi-table Excel regression: absent and stale stored category samples and numeric bounds must be replaced from Parquet on every description call; verify the targeted service test fails before implementation and passes afterward.
- [x] 1.2 Read exact categories for classified strings and finite bounds for numeric columns of all requested authorized tables in one guarded DuckDB description job, preserving table and column order; verify mixed-batch, empty/non-finite, and repeated-call service tests pass.
- [x] 1.3 Cover denied documents, unreadable artifacts (including tables without value columns), signed-URL redaction, and the configured dataset scan cap; verify targeted service tests pass and inspect the guarded DuckDB job path for capacity, timeout, and cancellation handling.

## 2. Ingestion and contracts

- [x] 2.1 Remove persisted category samples and numeric-bound calculations from CSV and Excel ingestion while retaining numeric types and categorical verdicts; verify the targeted CSV and Excel producer tests show no stored values in newly ingested artifacts.
- [x] 2.2 Update the current tabular design documentation to describe call-time category and bound reads and their cost/limits; verify the old ingestion-only statement is gone and the document matches the implemented behavior.

## 3. Verification and close-out

- [x] 3.1 Backend `make test PYTEST_OPTS='-q'`: 1448 passed, 27 deselected, 23 warnings. After the final review fixes, description service tests: 8 passed, 54 deselected, 3 warnings. Root `make code-quality`: passed across all modules; backend basedpyright reported 0 errors, 0 warnings, 0 notes. The 20-table workbook description completed in approximately 0.78 seconds, below the configured timeout.
- [x] 3.2 Reconciled the plan and implementation, validated the delta with `openspec validate compute-tabular-bounds-on-description --strict`, synced and validated the main spec with `openspec validate --specs`, and archived the completed change; confirmed no active change remains.
