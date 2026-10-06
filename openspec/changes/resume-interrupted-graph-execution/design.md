## Context

See proposal.md for the consumer and scope. The existing branch already provides
synchronous Graph durability, explicit continuation and PostgreSQL/SQLite admission.
The revised scope was approved in conversation: preserve Marc's prepared publication,
ask the user when execution is unfinished, and avoid distributed recovery machinery.
One active execution per Graph conversation is a usage constraint, not an enforced
global scheduling guarantee. Graph is not yet in production for this consumer.

## Goals / Non-Goals

**Goals:** preserve prepared state, explicitly resume using current authorization,
and make uncertainty visible. The reference workflow is prepare -> publish -> finalize.

**Non-Goals:** process-death detection, automatic retries, concurrent new-turn/Restart
coordination, late-writer fencing, network-partition recovery, exactly-once delivery,
a generic external-effect journal, ReAct/Deep changes, or reconstructing the lost
user message. This slice does not satisfy the whole of #2892.

## Decisions

### 1. Preserve the boundary between preparation and publication

Keep `durability="sync"` for Graph. The agent's preparation step records both the exact
operation content and its stable business identity. The publication step uses that
identity to replay or query the destination; finalization uses a persisted receipt.
Checkpoint identity is a runtime continuation identity, not the business idempotency key.

No runtime-specific publication model is added. A domain-neutral test destination proves
the contract inside Fred; fred-rags validates its real adapter separately. A received
but unpersisted acknowledgement still requires safe replay/reconciliation. A failure
before durable preparation prevents publication.

### 2. Preserve unfinished work instead of inferring why it stopped

Keep the existing `execution_interrupted` wire kind for compatibility within the branch,
but describe it as unfinished execution. Pending steps without a HITL pause do not
prove that an owner died or that an external operation failed.

Remove `_end_unfinished_run`, its `_RUN_KEY` ownership metadata and cleanup-only helpers
and tests where no other consumer needs them. Do not clear pending steps on node error,
step limit or missing completion. Keep error reporting; do not convert the error itself
into success or automatically resume it. A later request discovers whatever unfinished
state the engine retained. Completed state and ordinary HITL retain their existing paths.
Verify native engine behavior for errors and limits before claiming acceptance; if it
cannot support this contract, report the concrete gap instead of inventing recovery state.

This supersedes the former terminal-cleanup requirement and its race-fixing task. The
chosen response to that finding is deletion, not atomic cleanup or additional locks.

### 3. A user decision is explicit and does not establish an external outcome

Reuse the existing card, localized in EN/FR. Explain that the previous execution is
unfinished and an external operation may already have happened. Present:

- Continue: resume the pending work with the persisted state and current authorization.
- Restart: start a new turn; warn that prior external effects are not undone.
- Later: dismiss locally without a request, state mutation or erasure; the next message
  rediscovers unfinished work. No new persisted dismissed state is needed.

The author must make the continued operation replayable or reconcilable. A generic
confirmation does not make an unsafe operation safe; unsupported destinations require
external verification and must not be blindly retried. This is an authoring constraint,
not a new runtime capability registry or automatic safety classifier.

Continue requires its current opaque interruption id and empty input, with no HITL
resume payload. It preserves the composer draft and adds no user row. Restart keeps
this branch's original submitted text/command behavior; rebuilding attachments or a
new draft-editing flow is not added. Discovery on conversation load remains out of scope.

Use the existing HTTP acceptance callback to distinguish a refused request from an
accepted stream: restore controls on a known refusal and consume Stop intent only on
acceptance. A transport failure after acceptance is uncertain; do not retry automatically.
Stop remains a session-local browser intent, retained across navigation but not reload.

### 4. Retain bounded admission, not a distributed ownership promise

Keep the current PostgreSQL transaction advisory lock and local SQLite file lock for
technical continuations, including their pool-capacity guard and cancellation cleanup.
No new lock protocol, TTL, lease or heartbeat is introduced. Providers that cannot
support the existing admission explicitly reject Continue.

Close and await `compiled.astream` inside the admission scope, as well as the Fred
wrappers, so local engine teardown finishes before release. Test closure during a
progress event, not only after final output. This does not prove a cancelled external
request had no effect.

The supported usage has one active execution per conversation. The existing lock only
rejects competing continuations while held; it does not coordinate ordinary runs or
Restart. Users must stop/wait for other executions before resuming. Do not infer owner
death from elapsed time or offer a force-unlock action. Cross-pod races and late writes
outside that usage contract remain explicitly unsupported.

### 5. Keep API and security convergence

Retain the event/request types and regenerate the runtime client after validation changes.
Authorization and current runtime binding precede discovery/continuation. A stale id is
rejected without running a node. Reporting unfinished work creates no fictitious user
history or completed-turn KPI. Non-Graph Continue remains rejected; ReAct/Deep are unchanged.
Existing invoke/child/OpenAI-compatible callers retain their documented restart behavior;
this is not an assurance that their external operations can safely be repeated.

## Risks / Trade-offs

- Preserving failed work can offer a retry that fails again: show the error, require an
  explicit decision and allow Restart/Later; no automatic retry policy.
- A running execution elsewhere can look unfinished: state that uncertainty and require
  single-active-execution usage; no claim that user confirmation establishes exclusivity.
- A repeated external call can duplicate an effect: use the author's stable identity and
  destination contract; Restart is not rollback.
- Sync persistence adds awaited database latency; a PostgreSQL continuation holds one
  extra connection. Retain existing bounded admission, without claiming measured throughput.
- A deployment changing graph topology/state may invalidate continuation: this slice
  assumes a compatible agent definition, without adding a version-negotiation system.

## Migration Plan

Update existing runtime contract, UX description, migration note and PR description when
implementing the delta. Deploy frontend and runtime together; identify changed behavior
after node errors and pending pre-upgrade checkpoints. No schema migration is introduced.
Preserve provider prerequisites from the existing migration note. Rollback restores
previous restart behavior and does not undo external publications.

## Follow-up for ReAct and Deep

Later examine their shared executor's persistence boundaries, tool-result reuse and
stream teardown against this concrete Graph example. Do not add Continue to those
engines or claim generic external-effect guarantees in this change.
