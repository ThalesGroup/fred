---
schema: 1
title: "Explicitly continue unfinished Graph work"
impact: none
configuration: none
configuration_reason: "Runtime and frontend behaviour only; no configuration key, default or chart value changes."
no_action_reason: "No schema or data migration: continuation uses existing checkpoints and PostgreSQL or local file-backed SQLite locks. Keep one active execution per conversation; an interrupted step may repeat an external effect, so agent authors must ensure idempotency as described in the source note."
---
## Applicability

Existing Fred deployments upgrading to this release, for Graph agents only.

## Prerequisites

Deploy the runtime and the frontend of the same release. Technical continuation
requires PostgreSQL (a pool with at least two base connections, or NullPool), or
file-backed SQLite on a local POSIX filesystem with permission to create
`<database>.graph-locks/`. Other providers explicitly refuse continuation.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. Graph checkpoints are now written synchronously per step.
A conversation whose Graph thread was already left with pending steps before the
upgrade is offered **Continue** or **Restart** on its next message. Node errors and step limits retain pending work instead of automatically clearing
it. A later message offers explicit recovery; no automatic retry is introduced.

## Validation

Stop the runtime pod while a Graph agent is between two steps, restart it, and
send a message in that conversation: the chat shows the interruption card, and
**Continue** finishes the run without repeating completed steps.
Kill the pod again during that continuation, before the step completes: a new
pod can continue the same checkpoint without deleting any claim.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.
After rollback, the next message restarts an interrupted Graph run, as before.

## Limitations

ReAct and Deep agents keep restarting after a lost process. A frontend older than
the runtime shows no answer for a turn on an interrupted Graph thread. Direct
`/agents/execute` API clients reusing such a session receive the new
`execution_interrupted` event and must answer it with `interrupted_action`; the
OpenAI-compatible route restarts automatically. A run still executing on another
replica or tab cannot be told apart from a lost one.

Concurrent technical continuations use owner-lifetime locks. PostgreSQL reserves
at most half the pool's base connections for continuations so checkpoint writes
can progress; capacity exhaustion is rejected with a retryable user message.
Old `continue:` HITL claim rows no longer affect continuation and require no
manual purge. Ordinary HITL single-use claims remain unchanged.

SQLite keeps empty lock files; do not delete or replace them while any runtime
process is running. They may be removed with all runtime processes stopped.
An interrupted step may repeat an already committed external effect. The agent
author owns idempotent replay or reconciliation of the same prepared operation;
checkpoint storage is not atomic with an external destination.

## Supported usage and external effects

Use one active execution per Graph conversation and a compatible agent definition.
The continuation lock does not coordinate ordinary new turns or Restart across pods;
stop or wait for other executions before recovering. Fred reports unfinished work,
not proven owner death. Restart is not rollback; Later leaves the checkpoint intact.
Persist stable operation identity and content in a preparation step, reconcile/replay
publication through the destination's idempotency contract, then persist its receipt
before finalization. An error or timeout is not proof of no external effect.
