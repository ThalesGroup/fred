# PERF-05 — task acknowledgement reads the same row three times

- **GitHub issue:** parent
  [#2110](https://github.com/ThalesGroup/fred/issues/2110); dedicated issue not
  yet created
- **Priority:** P3
- **Verdict:** confirmed
- **Owner:** unassigned

## Production impact

One task acknowledgement performs three database reads of the same task: one
for route-level authorization, one for the needs-attention business rule, and
one before updating the row. A team-scoped request can also perform a ReBAC
access check between the first and second reads.

The operations are asynchronous and acknowledgement is a low-frequency
terminal-task action, so this is not an event-loop blocker or a release
blocker. It is avoidable database latency and leaves room for the row state to
change between authorization, predicate evaluation, and update.

## Exact call chain

```text
POST /tasks/{task_id}/ack
  -> TaskService.get_run                 # database read 1
  -> authorize_task_access              # optional remote ReBAC check
  -> TaskService.acknowledge
    -> TaskStore.get_run                 # database read 2
    -> needs_attention(...)
    -> TaskStore.acknowledge
      -> AsyncSession.get(TaskRunRow)    # database read 3
      -> set acknowledged fields
```

Both control-plane and knowledge-flow routes have this shape.

## Evidence

- `apps/control-plane-backend/control_plane_backend/tasks/api.py:119-134`
  loads the row for authorization, then calls `service.acknowledge`.
- `apps/knowledge-flow-backend/knowledge_flow_backend/features/tasks/controller.py:88-105`
  repeats the same route pattern.
- `libs/fred-core/fred_core/tasks/service.py:126-141` loads the row again,
  evaluates `needs_attention`, then calls the store update.
- `libs/fred-core/fred_core/tasks/store.py:300-316` loads the row a third time
  inside the write session before setting acknowledgement fields.

## What is proven

- A normal successful acknowledgement executes three task-row reads.
- Both backend entry points share the redundant service/store path.
- The calls are async database operations rather than synchronous event-loop
  blockers.
- Authorization and the needs-attention rule deliberately live at different
  layers today.

## What is not proven

- Measured production latency or database load from acknowledgements.
- Whether SQLAlchemy identity-map reuse could remove a physical query in any
  deployment; the current calls do not share one explicit session, so code
  cannot rely on that.
- The desired concurrency semantics if task state changes while an
  acknowledgement is in flight.

## Minimal fix direction

Consolidate the read, authorization input, needs-attention check, and update
around one explicit session/transaction without duplicating the business
predicate. A minimal design may pass the already-loaded row and session
through the service/store boundary, or use an atomic conditional update after
authorization if its predicate can precisely preserve `needs_attention`.

Choose the approach only after defining the race semantics. The fix must not
broaden who may acknowledge a task or allow a stale failed/cancelled state to
overwrite a newer run state.

## Rejected alternatives

- **Remove the route read:** authorization needs task scope/ownership data.
- **Remove the service read without changing the contract:** the service owns
  the needs-attention rule and cannot silently stop enforcing it.
- **Move all checks into both routers:** that duplicates business logic across
  control-plane and knowledge-flow.
- **Optimize before higher-priority findings:** this is low frequency and P3.

## Acceptance criteria

- A successful acknowledgement performs one task-row read, or the minimum
  explicitly justified query count for an atomic conditional update.
- Control-plane and knowledge-flow keep identical authorization and HTTP
  behavior.
- `needs_attention` remains the single business-rule source of truth.
- Concurrent state changes have a documented, tested outcome.
- A query-count regression test prevents the three-read pattern from
  returning.

## Tests and load scenario

- Add a SQL query-count assertion for successful, not-found, and
  not-acknowledgeable requests.
- Test both backend routes against the same service behavior.
- Race acknowledgement with a task state/step transition and verify the
  chosen transaction semantics.
- A load test is optional after the query-count fix; if run, use a burst of
  terminal-task acknowledgements and record database pool wait and p95.

## Decision log

- **2026-07-26:** recorded as confirmed P3. Defer implementation behind
  PERF-01 through PERF-04 unless database measurements raise its priority.

## Resolution evidence

Not resolved. Add the dedicated issue, chosen transaction semantics, fix
commit, query-count results, and concurrency-test evidence here.
