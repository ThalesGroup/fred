---
name: fred-async-progress-reviewer
description: Review FRED asynchronous progress tracking and real-time task updates. Use when reviewing ingestion, erasure, evaluation, migration, scheduler, Temporal, task service, event bus, SSE, polling, retry, cancellation, rehydration, Redux task state, or UI progress indicators. Especially use for bugs where the UI misses steps, shows stale status, loses terminal state, or diverges between backend and frontend.
---

## Shared team policy

Read the active checkout's `AGENTS.md`, applicable nested instructions and
`fred-reconstruction-method` for domain/persistence work. Use that checkout's
arc42 and code; never load policy from a hardcoded personal Fred directory.
Apply the reuse, replacement and production-code reduction acceptance rule.
This is a bounded review unless fixes are requested. Propose verification needs
without automatically starting tests, load campaigns or independent agents.

# FRED Async Progress Reviewer

Review async progress as a state-machine and failure-mode problem. Trace durable state and delivery guarantees within the agreed contract; passing
unit tests alone does not establish reconnect or cross-replica correctness.
Inspect the existing shared lifecycle before proposing another bus, queue, retry
layer or frontend state machine. Separate target guarantees from observed behavior.

## Required Workflow

1. Read the repo instructions first.
2. Draw the event path in text:
   - producer
   - durable store write
   - live bus publish
   - replay endpoint
   - SSE or polling client
   - frontend reducer
   - UI consumer
   - refresh/refetch after terminal state
3. Identify the state machine: states, terminal states, retries, cancellation, partial failure, and stale execution reconciliation.
4. Check every boundary for ordering, idempotence, authorization, and reconnect behavior.
5. Produce findings first; then provide an invariant checklist.

## Non-Negotiable Invariants

- A terminal event must never be lost.
- Replay plus live subscription must not have a gap where an event can disappear.
- `Last-Event-ID` or equivalent cursor must be monotonic and dedup-safe.
- A client reconnect must eventually converge to the durable task state.
- A page reload must rediscover every non-terminal task the user is allowed to see.
- A task visible in list/history must have compatible detail/stream authorization.
- The task `kind` must route to the backend that owns its events.
- Sparse events must not erase previously known target, owner, or display metadata unless explicitly intended.
- Retryable backend failures must leave an observable state, not a silent infinite `running`.
- Polling may be a fallback, but it must be named as such; do not call it real time.

## Race Checklist

Look specifically for:

- replay-before-subscribe races
- publish-before-commit or commit-before-publish inconsistencies
- multiple workers emitting events for the same task
- terminal event emitted while the stream is between reads
- browser refresh after task creation but before first event
- backend restart with active tasks
- network drop after event delivery but before reducer commit
- 4xx SSE failures treated as non-retryable when auth or routing can change
- enum/kind mismatch causing the client to connect to the wrong backend

## Review Output

Use this structure:

1. Findings, highest severity first.
2. Event-path evidence, with file/line references.
3. Invariant verdicts: Proven / Broken / Untested.
4. Test gaps.
5. Suggested minimal fix direction, favoring shared code and deletion of parallel paths.

## Minimum Test Expectations

Expect focused tests for:

- replay plus live subscribe without gaps
- reconnect from a non-terminal cursor
- terminal event closes or converges the UI
- task kind routes to the owning backend
- authorization parity between list and stream
- frontend reducer handles duplicate, out-of-order, sparse, and terminal events
- reload/rehydration registers active tasks from each producer
