## 1. Excel attachment ingestion

- [x] 1.1 Reuse corpus `ExcelProcessor` and `ExcelTableRegistrationProcessor` for new Excel attachments, publish `output.md`, skip vector preview indexing, and return tabular availability; verify a multi-sheet fast-ingest test can describe all sheets and query rows beyond the old preview cap.
- [x] 1.2 Reject corrupt or tableless workbooks without a successful attachment and compensate uploaded artifacts after any failed stage; verify focused failure and cleanup tests.

## 2. Scope and lifecycle

- [x] 2.1 Resolve all tables of an explicitly named owned Excel attachment in tabular schema, search, and SQL paths without exposing them to other users or blind listing; verify owner, non-owner, and ReBAC-disabled tests.
- [x] 2.2 Classify and delete both CSV and multi-table Excel attachment artifacts through owner and platform lifecycle paths; verify all Parquet objects, `output.md`, and metadata are removed.

## 3. Agent behavior

- [x] 3.1 Guide the agent to use Excel and CSV tabular schemas and queries, including the `output.md` roadmap, while allowing old text-backed Excel attachments to use the text path; verify focused runtime prompt tests.
- [x] 3.2 Keep selected document reading tools useful for text attachments and make calls on tabular-only attachments explicitly bounded or unavailable; verify focused content and capability tests do not present partial spreadsheet previews as full reads.

## 4. Documentation and verification

- [x] 4.1 Update the session attachment design, Help Center, UX note, and existing PR migration note for new Excel behavior and legacy compatibility; verify the migration declaration and strict OpenSpec validation.
- [x] 4.2 Run focused backend and frontend tests, review the diff, and run root code quality once before push; record actual results in this change and PR #2838.

## 5. Common discovery follow-up (issue #3007)

- [x] 5.1 Extend the existing runtime MCP binding to obtain persisted attachments through the control-plane's owned-session route, reuse the active context and source flags, and inject bounded attachment UIDs into `list_tabular_documents`. Hide and enforce runtime-owned arguments. Verify no-argument calls, source ceilings, forged arguments, lookup failures, same-user cross-conversation isolation and shared-client turn isolation in focused runtime tests.
- [x] 5.2 Extend the existing tabular listing with optional attachment scope and source flags, reuse `_resolve_authorized_datasets`, `_resolve_owned_attachment_datasets` and document grouping, and expose `source_kind` plus available `tag_names` in the existing response. Verify corpus/attachment union, attachments-only, corpus-only, neither source, same-name UIDs, all Excel tables, ReBAC enabled/disabled, uploader isolation, missing/deleted/unready/legacy artifacts and absence of extra catalog scans or Parquet reads in service/controller tests.
- [x] 5.3 Apply the same effective scope at existing describe, SQL and value-search invocation seams without a parallel authorization framework. Verify corpus selections preserve enabled attachments, listed UIDs remain queryable beyond preview limits, and guessed UIDs cannot bypass source or conversation boundaries. Run a synthetic list/describe/query check through ReAct and Deep and check affected Graph MCP consumers.
- [x] 5.4 Update the existing tabular instructions and attachment prompt to describe one discovery flow, one short provenance note and mandatory schemas before SQL; retain the legacy text fallback. Reconcile the existing attachment design and runtime contract, regenerate affected OpenAPI/clients, and add the follow-up PR's migration note. Verify prompt tests, generated diffs and strict OpenSpec/migration validation.
- [x] 5.5 Run the root quality check once near commit/push, apply the full-branch author review and independent read-only review, and run the performance review for the new scoped lookup and MCP binding. Record actual verification and review dispositions here and in the PR, then sync/archive the reconciled change after implementation.

## Verification evidence for completed ingestion groundwork

- Backend ingestion and delete authorization: 32 focused tests passed. Tabular service: 65 tests passed, including a two-sheet attachment, `output.md`, a row after the old 20-row preview, search, owner isolation, and ReBAC-disabled listing. Content reader fallback: 7 tests passed.
- Runtime prompt: 53 tests passed. Frontend pack selection: 12 tests passed.
- `openspec validate tabular-excel-chat-attachments --strict` and `openspec validate merge-attachments-into-team-resources --strict` passed. `make migration-check MIGRATION_BASE=origin/swift` passed. Root `make code-quality` passed through every module, including frontend TypeScript, Prettier, and ESLint.
- Diff reviewed for table registration, cleanup, owner checks, legacy text attachments, and Simple pack selection.

## Verification evidence for common discovery

- Runtime: 73 tests passed in `test_context_aware_tool.py` and `test_react_prompting.py`. Covers forced source ceilings, forged arguments, per-conversation refresh/deletion, refused authority, selection union, one scripted ReAct turn, and the tools registered in the compiled Deep graph. A full scripted Deep model-loop smoke and the existing scratchpad baseline both timed out in this environment; model-loop behavior is excluded from this verification, not reported as passing.
- Knowledge Flow: 14 focused service cases passed for source union, owner/library/document selections and readiness; two additional isolation cases passed, one overlapping readiness coverage. CSV processors and real Parquet queries are exercised. The existing TestClient listing case stalled; its HTTP response contract was verified instead through actual MCP HTTP and the browser fixture.
- Playwright Chromium: production tabular controller, CSV/Excel processors, runtime wrapper and actual MCP HTTP transport over isolated synthetic stores/session authority. Both sources and each source alone passed, with correct origins/library names, both Excel sheets, all 30 rows and 10 rows after the old preview boundary. Forged arguments, unscoped listing and another conversation passed. No page errors. Local evidence: `/tmp/fred-3007-playwright/results.json` and `corpus-and-attachments.png`; fixtures and screenshots are not committed.
- API generation used the worktree modules and an isolated storage configuration preserving scheduler routes: `CONFIG_FILE=/tmp/fred-3007-openapi/config.yaml PYTHONPATH=.:../../libs/fred-runtime:../../libs/fred-sdk:../../libs/fred-core:../../libs/fred-pod <existing-kf-venv>/bin/python ../../scripts/generate_openapi.py knowledge_flow_backend`, followed by `npx --no-install @rtk-query/codegen-openapi src/slices/knowledgeFlow/knowledgeFlowOpenApiConfig.json`. Generated client retains processing endpoints/hooks and adds only tabular scope/provenance fields.
- Root `make code-quality` passed all modules using existing Python environments with local source paths and frozen frontend dependencies installed in this worktree. Strict validation of this change, the migration declaration check against `origin/swift`, and `git diff --check` passed.
- Main specs validate after sync; this new main spec also passes strict validation. A strict check of every main spec reports an existing placeholder Purpose in `frontend-surface-scale`, unrelated to this change.
- Independent full local-diff correctness/performance review against `origin/swift` at `7dafb6f6c6f39eb457bbccad157ec6bcd8201b97`: generated-client regression and library/document intersection were fixed, checked independently, and closed. Reviewed runtime binding, corpus/attachment authorization, list/describe/query/search, actual MCP schema conversion, affected consumers, docs and migration. No additional catalog scan or Parquet inventory read, blocking hot-path I/O or new metric visibility defect was found. Load contention at 200 callers/four replicas, live IdP/delegation and a deployed full chat UI are excluded; the browser uses synthetic authority and actual scoped tool transport.
