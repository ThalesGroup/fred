## Current scope verification — 2026-10-04

The historical sections below describe earlier revisions, including superseded
terminal cleanup and permanent technical claims. Current scope follows design.md.

Automated verification of the revised implementation:

- SDK execution contracts: 53 passed.
- Targeted runtime continuation, admission, HITL and storage suites: 86 passed,
  4 integration cases deselected.
- Full offline runtime suite: 1,777 passed, 11 skipped (optional fastapi_mcp),
  21 integration cases deselected. PostgreSQL was not rerun in this session.
- Frontend chat, managed-chat and HITL suites: 132 passed across three files.
- Root `make code-quality`: exit 0 across all modules. The developer will run
  final root `make test` and code-quality after the remaining manual acceptance.

Verification exposed a real failed-checkpoint boundary: completed pending task
writes can leave snapshot.next empty while snapshot.tasks still needs settlement.
Discovery now uses tasks, and continuation preserves the engine's cached writes.
The preparation/receipt persistence regressions and full runtime suite pass.

Independent read-only review covered origin/swift ffa228f4c04ff3b918889c14d0d4580c3cce6d67
through 2ed7c78c4 plus the validation corrections: production Graph/SDK paths,
generated client, UI consumers, provider admission, tests and documentation.
No remaining actionable production defect was identified within the approved
single-active-execution scope. Minimality review retained existing provider admission
and native task reuse; no distributed recovery mechanisms were added.

Manual evidence from the developer's local Test Assistant session:

- Deliberate crash leaves a recoverable execution and exposes the three choices.
- Continue retries the failing node, without a new user message; the pending draft remains.
- Restart executes that draft once, produces a normal Echo answer and clears the composer.
- The developer reports the subsequent chat/history checks look correct.
- Two successive errors lack a visible indication that the second was a retry:
  recorded as a UX observation, not a demonstrated execution defect.

Still pending: explicit Later confirmation, successful continuation after manual
interruption, and end-to-end publication replay with a suitable destination.
The automated idempotent fixture covers committed publication with response loss,
process loss, preparation/receipt persistence and durable receipt reuse; it does not
prove the real fred-rags adapter. No load campaign or distributed ownership validation
was performed. ReAct/Deep recovery remains excluded.

The runtime client was regenerated from the SDK using
`uv run python scripts/generate_openapi.py` in fred-runtime and
`npx --no-install @rtk-query/codegen-openapi src/slices/runtime/runtimeOpenApiConfig.json`
in the frontend. Keep the change active until remaining acceptance is settled;
unperformed interactive checks are not recorded as passes.

---

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

## Scoped owner-loss correction (2026-10-02)

The developer confirmed PostgreSQL and SQLite owner-lifetime admission for technical
continuations. External-effect idempotency/reconciliation belongs to the agent author;
there is no atomic transaction or exactly-once promise for external effects.

`GraphExecutor` now holds admission around a continuation and retains LangGraph's
checkpoint and pending task results. The permanent technical HITL claim and its
duplicate checkpoint-validation method are removed; ordinary HITL claims are unchanged.

Verification:

- Root `make code-quality`: exit 0. Raw basedpyright on the three affected executor/store
  modules and both affected test files: 0 errors, 0 warnings, without baseline masking.
- Final runtime offline suite: 1,746 passed, 11 skipped (missing optional `fastapi_mcp`),
  21 integration cases deselected.
- Targeted runtime suites including unchanged storage and HITL suites: 82 passed before
  the final legacy-claim regression. The final two changed suites pass 30 cases with
  PostgreSQL 16, including that regression.
- The four PostgreSQL integration cases also pass on PostgreSQL 17. They cover mutual
  exclusion, real process death, configured server timers, and reserved checkpoint
  connection capacity. Both databases were isolated temporary Docker containers.
- `make migration-check`: valid. `openspec validate resume-interrupted-graph-execution
  --strict`: valid. `git diff --check`: clean.

New behaviour-locking evidence includes:

- A process dies inside a continuation through the public pod endpoint; a new process
  finishes from the same step without repeating preparation or deleting a claim.
- A live owner rejects a competitor. Killing the owner releases admission on both
  SQLite and PostgreSQL; different Graph threads are independently locked.
- Multiple continuations retain a completed tool-task result, with one external tool
  invocation. Closing the SDK stream releases admission immediately; cancellation
  during SQLite worker acquisition does not leak a late-acquired file lock.
- Previously burned `continue:` HITL claims are ignored without modifying their rows.
- PostgreSQL timers configured to 100 ms do not steal a 300 ms owner. `SET LOCAL`
  settings restore after exit, including PostgreSQL 17's `transaction_timeout`.

Independent correctness/performance review found one server-timer defect; it was fixed
and re-reviewed with no remaining blocker in this slice. Admission holds one PostgreSQL
connection per continuation, with a pool-shared local capacity guard leaving checkpoint
headroom. SQLite filesystem acquisition runs in a worker thread. No load campaign was
run, and no new KPI dimensions, public models, migrations, leases or heartbeats were added.

Review point 3 (concurrent failure cleanup), new-turn/Restart coordination and late-writer
fencing remain deferred. The change stays active; it is not archived by this commit.
