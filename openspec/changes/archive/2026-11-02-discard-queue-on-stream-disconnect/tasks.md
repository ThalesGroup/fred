## 1. Simplify the final PR

- [x] 1.1 Restore the local queue and remove durable routes, SDK identity, history acknowledgement and generated client/store plumbing; verify the cumulative diff and absence of recovery callers.
- [x] 1.2 Verify interruption/navigation clearing, late-callback isolation and text-only retry/removal with focused frontend tests; preserve normal completion and HITL behavior.
- [x] 1.3 Verify cancellation-protected teardown, heartbeat shutdown, replacement ownership and bounded expiry with focused runtime and real PostgreSQL tests.

## 2. Close-out

- [x] 2.1 Reconcile current contracts/specs and the impact-none operator note; verify API generation, migration validation, raw typing and root quality.
- [x] 2.2 Review the entire final PR against its merge base independently, record findings and evidence, then sync/archive and publish the simplified PR with no unrelated changes.

## Verification and cumulative review

- Frontend: 223 passed across `useManagedChat.test.tsx`, `ManagedChatPage.test.tsx` and `useChatSse.test.tsx`. The final uncertain-removal UI-state variant also passed independently.
- Runtime: 143 passed across `test_turn_steering.py` and `test_agent_app.py`, including real PostgreSQL consume/sweep/renew/replacement cases on a dedicated temporary database.
- Raw basedpyright: 271 runtime files, 0 errors / 7 warnings. API regeneration returns the generated public contract to the merge base. Migration declaration and all 38 capability specs validate; strict change validation passes.
- Full cumulative author and independent review: merge-base `7a2bbcbc5c8cc34f0eb7d9472715d57ca7faf35f`, parent HEAD `75f613597368409f5a4429e131baa16b12446781`, including working and untracked changes. Covered real UI consumers, local queue ownership, navigation, stale promises, SSE EOF/abort/HITL, protected runtime teardown, SQL locks/expiry, generated/SDK retirement, localization and docs. Unrelated removed translation keys were detected, restored and verified; no finding remains.
- Exclusions: real browser, full test matrix, LLM/load campaign, image scan, separate Temporal PR #3398 and unrelated upstream commits. The reviewer did not rerun the author's suites. Existing temporary SQL steering remains shared across replicas; no new server-local queue, schema or configuration was introduced.
- Root `make code-quality` passed across all modules; frontend TypeScript, Prettier and ESLint passed. No Alembic file is added or changed.
- Simplified implementation `0d65986e2` published in draft PR #3399. Main specs are synchronized (38 validated); completed artifacts archived as `2026-11-02-discard-queue-on-stream-disconnect`.
