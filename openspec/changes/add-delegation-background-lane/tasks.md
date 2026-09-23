## 1. Presence

- [x] 1.4 Define the reconnect request, response run handle and SSE sequence in the
      existing runtime SDK/streaming contract; add its dated contract entry and
      regenerate clients. Verify mixed reconnect/execute input is rejected and
      clients can read the exposed handle and cursor. This precedes 1.1 and 1.5.
- [x] 1.1 Bind a foreground run to its stream and cancel it, with its children,
      after reconnect grace; separate the execution task from its response
      generator and implement atomic single attachment plus bounded replay.
      Verify owner authorization, replay order, no repeated tool execution, no
      deadline reset, buffer eviction, concurrent reconnect, another-person denial,
      owner revocation and close past grace ending with `cancelled`.
- [x] 1.2 Verify a test that no code path promotes a foreground run to background.
- [x] 1.3 Verify a test that resuming a human-paused run after the grace is a new
      admission with the current token and that the cancelled run makes no
      further execution/tool/data call; only the terminal lifecycle report remains
      permitted by the foundation contract.
- [x] 1.5 Wire the frontend to retain the run handle/cursor and reconnect through
      the existing stream endpoint with the current token; verify reconnect errors
      never trigger automatic new execution, completed replay is deduplicated by
      sequence, and ordinary new admissions remain unchanged.
- [ ] 1.6 Deployment tooling: preserve affinity to the admitting runtime pod and
      expose the run-handle response header to the frontend. Verify a two-replica
      reconnect succeeds through normal routing; force the wrong replica and
      confirm 404 without a new execution or a control-plane call. Verify 409 for
      unavailable replay and 410 for a known run cancelled after grace before
      enabling the presence rule in a deployment.
      In repository: the route behaviours and the run-handle header need no
      further work. Affinity itself is deliberately not built: the runtime's
      replica setting now records that foreground reconnect resolves against the
      admitting pod, so the runtime must stay at one replica until affine routing
      exists. Outstanding: the affinity mechanism itself and the two-replica and
      forced-wrong-replica runs, which need a multi-replica deployment.

## 2. Background tasks

- [x] 2.1 Add the agent-run task kind and detail model with the admission record
      as payload; verify model tests.
- [x] 2.2 Add the team-scoped start endpoint requiring the agent permission and
      writing the record server-side; verify a test that a person without the
      permission cannot start one and that the record cannot be shaped by the
      request beyond prompt and scope.
- [x] 2.3 Implement the scheduler activity: re-check standing and permission, fail
      closed, register with the runtime workload bearer, take the grant parameters
      from the record, run under the job budget, emit task events naming background
      mode; verify tests for each branch, including registration failure and no
      person session/token. Depends on the foundation's registration API and the
      single-subject standing enforcement and model migration.
- [x] 2.4 Extend the credential provider to read durable records; verify a test
      that a background call names the recorded person and that the audit names
      the mode.
- [x] 2.5 Listing and cancellation scoped to person and team admin; verify tests.

## 3. Schedules

- [x] 3.1 Schedule creation with explicit opt-in and the same record; each tick
      starts one task; verify tests that a removed permission or standing stops
      the next tick.

## 4. Verification

- [x] 4.1 A run starts with no session of the person's in existence and completes;
      registration/downstream context identifies the runtime and recorded person,
      logs exclude identifiers, no
      receiver consults the registry, and cancellation reaches the worker and its
      children. Verify scheduled ticks use the same admission and reporting path.
- [x] 4.2 Run focused tests, `make code-quality`, `make test`, and the hot-path
      performance review.
- [x] 4.3 Add synthetic-data regression tests for another
      person's reconnect/cancel/list, cross-team tasks, unauthorized schedule
      creation, record-field tampering and revoked permission at the next tick;
      verify no side effects on denial and no credential or content leakage.
      Apply the foundation's delegation logging policy.

## 5. Integration ownership

- [x] 5.1 Settle the foundation's registration contract and standing prerequisites
      before task execution work. Assign one owner to the reconnect SDK/OpenAPI
      and generated files, then separate runtime, frontend, scheduler and deployment
      write sets; serialize shared provider changes and task-state updates. Verify
      integration against one contract before enabling presence or background work.

## 6. Durable lifecycle regression coverage

- [x] 6.1 Add explicit default-off agent-run worker opt-in independent of the
      existing generic scheduler flag; verify shipped chart configuration still
      starts with delegation off and invalid explicit opt-in fails closed.
- [x] 6.2 Serialize fresh standing checks and background/schedule/occurrence
      persistence with deletion, including personal-team admissions. Verify paused
      and post-purge requests cannot recreate private prompts or task records.
- [x] 6.3 Recover a scheduled occurrence's missing execution binding on retry;
      verify cancellation reaches that execution, while missing/terminal records
      are not recreated or reset.
- [x] 6.4 Persist cancellation intent during dispatch and honor it after binding;
      verify both interleavings and recovery through a fresh task-service instance.
      Bind scheduled cancellation to its existing occurrence parent and verify
      cancellation before child start and while child cleanup is pending.
- [x] 6.5 Await nested runtime cleanup before task terminal reporting and activity
      completion; verify final, error, human-pause and cancellation paths with
      delayed cleanup.
- [x] 6.6 Review the combined lifecycle changes and run affected regressions
      before closing local acceptance; retain external rollout gaps below.

## Local verification

The SDK and generated client expose reconnect handles/cursors; the frontend uses
fresh credentials and never retries execution on a reconnect failure. Real route
and manager tests cover initial execution, replay, owner refusal, grace and limits.
The worker opt-in and dispatch/cleanup regressions pass, including cancellation
before child creation and awaited child cleanup. Worker cleanup follows
application shutdown. Durable admissions, task status, schedules and occurrence
claims are control-plane product state. Test bridges exercise real cancellation
interfaces with synthetic Temporal transport, including child cleanup and final
state. Task and lifecycle reporting use the workload bearer; no person token is
retained. Terminal task reasons preserve `child_limit_reached`.
Task-store tests prove an outer transaction rollback removes the new task and
that duplicate task IDs leave the transaction usable. Admission persistence reuses
the lock holder's session. Cross-component test evidence is recorded in the
foundation change's `tasks.md`.

## Unimplemented external gaps

Schedule this work after local implementation and regression verification across
all three changes, immediately before full end-to-end tests.

- Deployment tooling: scheduler enablement, reconnect affinity, workload identity,
  transport and shared-environment integration evidence remain unimplemented.
  Local scheduler/replay tests do not close these external rollout requirements.
- Evaluation-worker integration remains in the single-subject change's final
  integration phase; complete it before testing full evaluation campaigns.
