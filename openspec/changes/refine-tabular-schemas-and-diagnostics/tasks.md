## 1. Targeted compact descriptions

- [x] 1.1 Add exact `table_names` selection before value scans and the selected-dataset limit; verify omitted/empty/default, targeted, duplicate, unknown, ambiguous and unauthorized selectors with service/controller tests and assertions that unselected artifacts are not read.
- [x] 1.2 Project compact public column responses with `categorical_values`, numeric-only bounds and no legacy flags; keep stored classification readable and stop computing two-value verdicts. Verify exact category casing, changed/empty current categories, null numeric bounds, legacy metadata and CSV/Excel response parity.
- [x] 1.3 Update category/table-selection references in the SQL/tabular prompts, add approved 4A/4B only to the packaged tabular prompt, and update tool parameter descriptions, frontend schema parsing/rendering and generated Knowledge Flow OpenAPI/client; verify new and historical trace shapes and unchanged recorded call arguments.

## 2. Correct temporal ingestion

- [x] 2.1 Preserve recognized Excel temporal dtypes through extraction and Parquet export without partial conversion data loss; verify native/text dates, blanks, mixed invalid/ambiguous values, timezone meaning and no-coercion behavior through physical schema and value round trips.
- [x] 2.2 Verify current CSV temporal inference and describe/query parity, and document truthful typing of unchanged historical string artifacts and explicit reprocessing of the synthetic campaign workbook only; confirm unreprocessed VARCHAR is never advertised as datetime.

## 3. Scoped SQL diagnostics

- [x] 3.1 Enrich supported binder errors from validated SQL scopes and already mounted schema metadata; test missing and ambiguous columns, quoted aliases and CTE/subquery projection cases, and assert unreferenced tables are neither consulted, read nor mounted.
- [x] 3.2 Verify enriched SQL diagnostics through the existing MCP/runtime/trusted drawer path for live and historical results; retain safe fallback, redaction, cancellation and genuine authority-loss behavior with focused integration tests.

## 4. Validation and review

- [ ] 4.1 Measure old/new description sizes using the same synthetic workbook and replay the retained failing SQL plus numerical references after deliberate fixture reprocessing. Report execution success separately from answer correctness and distinguish fresh model trials from isolated SQL checks.
- [ ] 4.2 Run root `make code-quality`, affected integration checks and focused concurrent description/query checks within existing capacity limits; record results and verify no cross-request/pod-local correctness state was introduced.
- [ ] 4.3 Apply the full `audit-branch` procedure against the actual target, obtain independent correctness and performance reviews for changed tool paths, record base/head, findings/dispositions and exclusions, and update migration guidance.
- [ ] 4.4 Reconcile the final implementation with these artifacts, sync delta specs and archive after verification; commit reviewable blocks and update the existing draft PR with the approved follow-up scope and evidence.
