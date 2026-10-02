## 1. SDK contracts

- [x] 1.1 Add `RuntimeEventKind.EXECUTION_INTERRUPTED` and `ExecutionInterruptedRuntimeEvent(request: HumanInputRequest, interruption_id: str)` to the `RuntimeEvent` union in `fred_sdk/contracts/runtime.py`. Verify that a round-trip unit test parses the event from its JSON dump.
- [x] 1.2 Add `interrupted_action` and `interruption_id` to `ExecutionConfig`. Add them to `RuntimeExecuteRequest` with the D5 validation rules: `continue` requires `interruption_id`, forbids `resume_payload` and allows empty input; `interruption_id` is only valid with `continue`. Verify with request-validation unit tests that cover each accepted and rejected combination.

## 2. Graph executor

- [x] 2.1 Pass `durability="sync"` to `astream` in `GraphExecutor._run`. Verify with a test that a checkpointer whose `aput` is held open keeps the next node from starting until it is released.
- [x] 2.2 Clear pending tasks with `aupdate_state(thread, None, as_node=END)` in the recursion-limit, exception and missing-completed-state branches of `_run`, best-effort and logged. Verify with tests that a node failure and a step-limit stop both leave `aget_state(...).next` empty and keep the channel values for carry-forward.
- [x] 2.3 In `_graph_input`, detect an interrupted thread: `next` non-empty, no interrupts, not a HITL resume. Compute `interruption_id` (D3) and make `_run` yield one `ExecutionInterruptedRuntimeEvent` (stage, step title from node metadata, `continue`/`restart` choices) and return, without running a node. Verify with a test that injects a lost run (pending `next`) and asserts exactly one event and zero node executions.
- [x] 2.4 Implement `continue`: if `interruption_id` matches the current head, return `None` input so that `astream(None)` resumes. Otherwise raise an execution error. Implement `restart` as today's fresh turn. Verify with tests for continue resuming at the interrupted node without re-running completed nodes, for a stale or unknown `interruption_id` rejected with zero node executions, and for `restart` starting at the entry node.
- [x] 2.5 Verify that cancellation keeps the pending step continuable: a test cancels the stream mid-node and asserts that the thread is reported as interrupted on the next turn.

## 3. Runtime admission and persistence

- [x] 3.1 Mirror the new request fields in `_AgentExecuteRequest` and `_to_internal_request`, and pass them into `ExecutionConfig`. Verify that the fields reach the executor with an `agent_app` test.
- [x] 3.2 Replace permanent HITL admission for technical `continue` with the PostgreSQL/SQLite owner-lifetime locks confirmed in D5. Reject concurrent continuations across processes, allow continuation after owner loss in the same step, and leave ordinary HITL admission unchanged. Refuse `continue` for non-Graph agents and ignore `restart` there. Do not discard LangGraph pending task results or infer owner death from elapsed time alone.
- [x] 3.3 Skip `_emit_turn_completed` and `_write_turn_history` when a payload of kind `execution_interrupted` is present, in both the streaming and non-streaming endpoints. Verify that a continued turn writes its assistant rows and no user row. Verify with history-store tests.
- [x] 3.4 Verify that an unauthorized caller to an interrupted conversation is rejected by the existing checks before any event is emitted, with an `agent_app` authorization test.

## 4. Process-restart acceptance

- [x] 4.1 Add a test that runs a Graph agent in a subprocess on a file-backed SQLite `FredSqlCheckpointer` and kills the process (`os._exit`) inside step N+1 after step N was persisted. Then, in the test process, reopen the same database, send a new turn (assert the event), send `continue` (assert that steps 1..N do not re-run, that step N+1 and the remaining steps complete, and that the final output is produced).
- [x] 4.2 Verify that existing HITL behaviour is unchanged by running the current HITL suites unmodified (`test_graph_capability_hitl.py`, `test_hitl_resume_langgraph_integration.py`, `test_sql_checkpointer_hitl_claim.py`).
- [x] 4.3 Through public pod execution, lose a process during a continuation in the same step, reopen persistent storage and continue successfully without repeating preparation or manually deleting a claim. Verify that a competing continuation is rejected while its owner remains live, and that persisted tool-task results are retained.

## 5. Frontend

- [x] 5.1 Regenerate the runtime OpenAPI and the frontend client (`make update-all-apis` in `apps/frontend`). Verify that the regenerated types include the new event and the request fields, with no hand-written duplicates.
- [x] 5.2 Handle `execution_interrupted` in `useChatSse`/`useManagedChat`: restore the draft, store the request and `interruption_id`, and render `HitlPrompt` with localized EN/FR strings for this stage. Verify with a hook/component test that the card shows both choices and the composer holds the draft.
- [x] 5.3 Wire Continue (`interrupted_action: "continue"`, `interruption_id`, empty input, no user bubble) and Restart (the restored draft with `restart`). Verify with tests asserting the exact request bodies.
- [x] 5.4 Record a per-session Stop flag that makes the next send carry `restart`, and clear it after that send. Verify with a test: Stop, then a new message, sends `restart`.

## 6. Quality, review and documentation

- [x] 6.1 Run `make code-quality` and `make test` from the repo root (Python and frontend) and confirm both are green. (code-quality green; make test green except 4 pre-existing frontend ask_user failures, see verification.md)
- [x] 6.2 Run the `fred-performance-reviewer` skill on the sync-durability change and record the outcome in this change.
- [x] 6.3 Run `/code-review` on the diff and resolve the findings.
- [x] 6.4 Add a dated entry in `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md` §8 (sync durability, interrupted execution, event, request fields, claim reuse) and update `docs/swift/ux/COMPONENT-UX.md` for the interruption card. Verify that both files are in the diff.
- [x] 6.5 Add the English migration note under `docs/swift/ops/migrations/` following `MIGRATION-GUIDES.md`. It covers no operator action, the frontend and runtime shipping together, and pre-existing threads with pending tasks. Verify that the release-policy check accepts it.
- [ ] 6.6 Record the verification evidence, comment on GitHub #2892 with the delivered slice and the remaining follow-ups, then archive the change.
- [ ] 6.7 Resolve the separately deferred failure-cleanup race (review point 3) before PR close-out. The owner-lifetime continuation fix does not claim to protect new turns/Restart or late checkpoint writers.
