## Verification evidence (2026-10-01, uncommitted working tree)

| Check | Result |
|---|---|
| `make code-quality` (repo root, every module) | exit 0 |
| `make test` (repo root) | exit 2. Every Python module is green (fred-sdk 502, fred-runtime 1736, fred-core 1029, control-plane 1444, knowledge-flow 1507, fred-agents 103, capabilities). The frontend has 4 failures out of 3176. |
| Those 4 frontend failures | `useChatSse.test.tsx` › "uses the current preparation for first-turn ask_user availability" (4 parameter cases). They fail identically with this change's frontend files stashed (4 failed / 42 passed on the baseline), so they predate this change. |
| `make migration-check` | valid, 1 new declaration |
| `openspec validate --strict` | valid |

## What the tests prove

`libs/fred-runtime/tests/test_graph_interrupted_execution.py` (16 tests) covers:

- **Real process loss**: a subprocess is killed with `os._exit` inside a step after the previous step was persisted. A new process reopens the same SQLite file, receives `execution_interrupted`, continues, and does not re-run the completed step.
- **Interruption reporting**: a lost run is reported and nothing runs. Continue re-runs only the interrupted step. A stale or unknown `interruption_id` is rejected, and so is a continue with nothing to continue. Restart starts from the entry step. `invoke()` restarts.
- **Clearing in a live process**: a node failure and the step limit leave nothing to continue, and the carry-forward values stay intact.
- **Sync durability**: the checkpoint is persisted before the next step starts. Mutation-checked: the test fails under `"async"`.
- **Pod-level behaviour**:
  - the interruption writes no history row;
  - a continue writes assistant rows and no user row;
  - a continue held by another replica is refused (mutation-checked against the claim key);
  - continue on a ReAct agent is refused;
  - an unauthorized caller gets a 403 before any event;
  - the OpenAI-compatible route restarts (mutation-checked).

The existing HITL suites (`test_graph_capability_hitl.py`, `test_hitl_resume_langgraph_integration.py`, `test_sql_checkpointer_hitl_claim.py`) and `test_graph_executor_storage.py` are unchanged and pass.

Frontend:

- `useChatSse.test.tsx` (4 new tests): the card and the draft restore; the continue body; the restart body; Stop then a single restart.
- `useManagedChat.test.tsx` (2 new tests): continue is not a HITL resume; restart re-sends the same wire text and command.

## Reviews

- **`fred-performance-reviewer`**: no blocking I/O and no new state. Sync durability serializes one existing checkpoint write per step, with no change in write volume or pool use. One pre-existing gap: `app.phase_latency_ms{phase}` is not Grafana-visible, because `phase` is not in `PROMETHEUS_ALLOWED_LABELS`. A load comparison is suggested.
- **`/code-review` (high)**:
  - Fixed: the OpenAI-compatible dead end (it now restarts); Restart re-sending the same text and command; a missing-id guard on continue; one shared optimistic-turn removal.
  - Documented as limitations in design.md and the migration note: a live run elsewhere looks interrupted; a burned claim after a same-step crash; Stop followed by a reload; the lost user row.

## Not proven

- PostgreSQL-specific concurrency. The claim reuses the HITL claim, whose PostgreSQL behaviour is covered by its own suite.
- Latency under load.

## PR #2903 review round (2026-10-02)

| Comment | Outcome | Evidence |
|---|---|---|
| P1: failure cleanup could clear a head that another run had advanced | Fixed. Cleanup is fenced on the run's start head or on its `fred_graph_run` checkpoint metadata. | `test_a_failing_run_never_clears_a_head_another_run_wrote`; the step-limit test also covers a checkpoint saved but not yet streamed |
| P2: the claim was started before validation | Fixed. The id is validated read-only before the claim is taken. | `test_pod_rejects_a_stale_continue_without_leaving_a_claim` |
| P2: Stop memory was hook-wide | Fixed. It is now a per-session set that survives `reset()`. | `useChatSse.test.tsx` › "after Stop, the next message of that session restarts, even after visiting another session" |
| P2: the card was lost when the request never started | Fixed. `send()` returns whether the turn started, and the card is restored otherwise. | `useManagedChat.test.tsx` › "keeps offering the choice when the continue request never started"; `useChatSse.test.tsx` › "send() reports whether the turn started" |
| Code-quality bot: "statement has no effect" (`await run` in the test helper) | No change. It awaits the cancelled task's teardown. | — |
