## 1. Durable runtime queue

- [x] 1.1 Extend the existing mailbox JSON and row transitions to preserve bounded waiting/offered/uncertain messages across start, take, end and expiration; verify legacy-entry compatibility, FIFO, bounds, owner isolation and empty-only deletion with focused mailbox tests.
- [x] 1.2 Add authenticated per-message queue read/mutation routes and ordinary execution queue identity, reusing existing contracts; verify repeated enqueue, concurrent claims, stale-turn refusal and unauthorized access with route tests and real PostgreSQL concurrency tests.
- [x] 1.3 Retain uncertain messages before dispatch and remove delivered entries only after durable history persistence; verify crashes before/after dispatch, lost SSE acknowledgements and history-write failure preserve recoverable text without automatic duplicates.
- [x] 1.4 Protect turn teardown with `complete_cleanup()` and sweep expired empty rows every 60 seconds; verify cancellation during teardown stops the heartbeat, preserves messages/replacement turns/HITL resumes, and controlled-time lifespan tests show periodic recovery.

## 2. Frontend and contracts

- [x] 2.1 Regenerate runtime OpenAPI/types/hooks from source, then replace local-only queue ownership with a server-backed view and existing controls; verify navigation/reload restoration, explicit resume, failed-save input preservation, late-response isolation and active-session FIFO draining in focused frontend tests.
- [x] 2.2 Update the runtime execution contract, relevant queue UX guidance and an `impact: minor` migration note covering old-replica draining and rollback with nonempty queues; verify API generation and root migration validation.

## 3. Verification and close-out

- [x] 3.1 Run affected offline suites, real PostgreSQL concurrent claim/renew/sweep coverage, applicable raw type checks and root quality checks once near commit; record commands, results and any unavailable environment here or in the PR.
- [x] 3.2 Complete full branch author review and independent read-only runtime performance/concurrency review; record actual base/head, affected consumers, findings/dispositions and verification in the task response or PR.
- [ ] 3.3 Reconcile verified behavior/evidence, validate and sync/archive this change using the repository procedures, then commit, push and open a draft PR targeting `swift` linked to #3396; verify only this coherent queue-recovery change is included.

## Verification and review evidence

- Runtime: `FRED_TEST_POSTGRES_URL=... .venv/bin/python -m pytest tests/test_turn_steering.py tests/test_history.py tests/test_agent_app.py -q`: 180 passed, including real PostgreSQL cross-replica claims/sweeps and deterministic lifespan scheduling/shutdown.
- SDK: `.venv/bin/python -m pytest tests/test_execution_contracts.py -q`: 57 passed.
- Frontend: targeted `vitest run` for `useManagedChat.test.tsx`, `ManagedChatPage.test.tsx` and `useChatSse.test.tsx`: 220 passed. Covers absent response data, restore without dispatch, personal alias, interrupted edit, failed enqueue identity reuse, and navigation during a post-save refresh.
- Raw basedpyright: runtime 271 files, 0 errors / 8 warnings; SDK 98 files, 0 errors / 0 warnings. Frontend `tsc --noEmit` passed.
- API generation: runtime `scripts/generate_openapi.py`, then frontend `npx --no-install @rtk-query/codegen-openapi src/slices/runtime/runtimeOpenApiConfig.json`.
- Author and independent review: base/head `origin/swift = 7a2bbcbc5c8cc34f0eb7d9472715d57ca7faf35f`, full queue working-tree delta including index and untracked files; backend, SDK, generated client, frontend, docs, and runtime performance/concurrency reviewed. Dispositions: independent queue DTO; reject queue IDs on nonstream/resume paths; preserve queue on checkpoint-only erasure; bounded sweep with retained rows outside expiration scan; canonical personal identity; generation checks after refresh and owner-checked drain callbacks. Final independent delta review found no open actionable finding.
- Exclusions: separate Temporal dependency worktree, external LLM/load campaigns, and image vulnerability scanning. PostgreSQL tests use a dedicated temporary database, not the application database. The live local runtime OpenAPI exposes the updated flat queue DTO.
- Root `make code-quality UV=<external uv 0.13.5>` passed across all modules. The external executable avoids the local bootstrap removing its own uv executable during sync. Both migration-note checks and strict OpenSpec validation passed. Final publication/archive remains pending below.
