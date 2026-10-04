## 1. Backend: read tasks by id

- [x] 1.1 `fred-core`: add a `task_ids` filter to the store and service `list_tasks`, and a repeated `task_id` parameter to `list_tasks_scoped` (scope `user` only, 1 to 50 values, terminal tasks included). Validation errors are 422.
- [x] 1.2 Expose `task_id` on the Knowledge Flow and Control Plane `GET /tasks` routes; regenerate both OpenAPI specs and frontend clients (`make update-knowledge-flow-api`, `make update-control-plane-api`).
- [x] 1.3 Tests in `fred-core` (store filter, authorization rules) and on the Knowledge Flow route (repeated parameter parsed, 51 ids rejected): own tasks by id in any state; unknown or foreign ids absent; more than 50 ids or another scope gives 422; unchanged behaviour without the parameter.

## 2. Frontend: polling loop and store

- [x] 2.1 `taskSnapshotsReceived` reducer and the `untracked` flag: terminal is final, absent means untracked, sparse fields kept. `selectActiveTasks`, `selectActiveCount` and `selectActiveTaskForTarget` exclude untracked tasks; "clear completed" removes them.
- [x] 2.2 `useTaskPolling`, mounted in `MainLayout` in place of `useTaskSseManager`: a sequential loop of reads every 5 s (2 s at first, raised after the k3d test showed phases lasting minutes), grouped by owning backend, chunks of 50, through the generated clients. It runs only while an active non-local task exists and reads right away when the tab becomes visible again. `dynamicBaseQuery` sends query arrays as repeated keys.
- [x] 2.3 Import panel and task card: "Following stopped" status, `untracked` badge state, local dismiss, in English and French.
- [x] 2.4 Delete `useTaskSseManager.ts` and its tests. Keep `taskEventReceived` and `lastSeq`, which chat attachments use.
- [x] 2.5 Tests with the real consumers (`useTaskPolling.test.tsx`: loop, generated clients, base query, store, import panel, document row): 13 tasks converge in one read per round; 60 tasks read as 50 + 10, never two reads in flight; convergence after a 401; while on another page; a failure stays a failure; a failed read changes nothing; an absent task becomes untracked and is no longer read; the loop stops when idle and restarts for a new task; immediate read on return to the foreground. Reducer cases in `taskSlice.test.ts`; serializer in `dynamicBaseQuery.test.ts`.

## 3. Documentation and verification

- [x] 3.1 Dated entry for the `GET /tasks` `task_id` parameter in `CONTROL-PLANE-PRODUCT-CONTRACT.md`; English migration note `docs/swift/ops/migrations/poll-task-progress-in-batches.md` (impact `none`).
- [x] 3.2 Root `make test` passed (run by the developer, 2026-10-03). Root `make code-quality` first failed on the import order in `fred_core/tasks/store.py`; after the fix, every Python check (ruff, import order, format, basedpyright) passed on `fred-core`, Knowledge Flow and Control Plane, and frontend `make code-quality` passed.
- [x] 3.3a `fred-async-progress-reviewer`: three findings, all fixed. A read that never answers is aborted after 15 s (it froze following for good). An untracked task refreshes its document (the row read a possibly stale copy). Control Plane routing and its route parameter are now tested.
- [x] 3.3c Codex review: an untracked migration could not be dismissed (the migration page sent a server acknowledgement that 404s, and listed the task as active). Fixed in `useTaskAcknowledgement` for every caller, with a test that fails without the fix; the migration page lists untracked tasks with the finished ones. The documented reconciliation delay was wrong (about 7 minutes, not 2) and is corrected in the migration note and the design.
- [x] 3.3b Contract review (Codex, `fred-contract-reviewer` grid): no P1. P2 fixed: a dismissed untracked task stayed listed for good, because visibility read only `state`; one `isFollowed` rule now drives the active, visible, count, sort and clear selectors, with tests that fail without it. P3 fixed: the spec now defines a round (batches of 50, one read in flight, then the interval) instead of "once per interval". P3 fixed: the docs said no caller sent query arrays; `GET /users/by-ids` did, and the serializer fixes its multi-author name resolution (documented in the design, the proposal and the migration note).
- [x] 3.3d Performance review (Codex, `fred-performance-reviewer` grid): no P1. P2 fixed: a batch of tasks settling together reloaded the same folder once per document; `useRefetchOnTaskSettled` now hands out a batch and the documents page reloads each folder, and the stats, once (hook and page tests, the page test fails with a per-document loop). P2 fixed: a real unmount and remount of MainLayout could leave the old round reading its remaining batches beside the new one; the loop chain is module state, cleanup cancels the read in flight, and a stopped loop reads no further batch (test fails with the previous hook). Server load stays an estimate, about 20 reads per second at the 5 s interval for 100 importing users with one tab each and 50 tasks or fewer; no measured latency is claimed.
- [x] 3.4 Manual check with the developer on k3d (2026-10-04, 13 PDFs into a recreated `arxivai` folder, `make k3d-fred` build of this branch). The panel and the table matched the worker at every capture (6 files extracting, the rest waiting, each file Done within a poll of its completion). The page stayed open past the first token's expiry (about 02:24 UTC) with no 401: 663 responses with status 200 and 1 with status 201. API traffic stayed at 40 to 53 requests per minute during the import, against 1 per minute on 2026-10-03 with per-task streams. A file finished while the user was on another page showed Done on return, without a reload. All 13 converged, including the three files stuck the day before. Reads stopped at the last completion (02:33:17) and none followed.

Verification so far (2026-10-03): frontend `tsc --noEmit` clean, eslint clean on
the touched folders, `vitest run` 3,200 passed and 7 skipped. The polling tests
fail against an empty loop (9/9), without the query-array serializer (3/9) and
without the read timeout (1/11). After the review fixes: `vitest run` 3,203
passed and 7 skipped; Control Plane `test_import_export_task_observability.py`
10 passed, including the by-id read as the creator and as another user.
`fred-core` tasks tests 106 passed, ruff clean. Knowledge Flow task tests 16
passed. Control Plane task tests 32 passed. `make migration-check` and
`openspec validate --strict` pass.
