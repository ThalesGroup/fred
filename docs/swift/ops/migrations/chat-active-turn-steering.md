---
schema: 1
after: [platform-skills-evolution]
title: "Post in-thread messages during active agent turns"
impact: minor
configuration: none
configuration_reason: "In-thread messages use the existing shared runtime SQL engine and session_history table."
---

## Applicability

Existing Fred deployments upgrading from the browser queue and runtime steering mailbox.

## Prerequisites

The runtime's shared PostgreSQL database must be available, as for checkpoints and history.

## Configuration

No configuration changes are required.

## Upgrade

Stop or drain old runtime replicas before applying the fred-runtime Alembic migration. The migration adds message identity and delivery state to `session_history` and drops `runtime_turn_steering`. Old replicas must not serve requests after the table is dropped. Start the new runtime replicas after migration, then deploy the matching frontend.

Messages still pending in the old runtime mailbox or browser queue are discarded. Already delivered conversation history and checkpoints remain. Tell users to resend an old pending message if it did not appear in their conversation after upgrade.

## Validation

With two runtime replicas, start a ReAct or Deep turn on one pod and submit another text message through the other. The message should appear in the thread with a pending indicator, remain at the bottom while tool events continue, and gain its final rank and a brief acknowledgement after the next model boundary. Reload the conversation and confirm its order. Repeat across a human-input pause and a restart. A message that misses the active turn should start as the next ordinary turn.

## Rollback

Stop the new runtime replicas before downgrading the migration. The downgrade recreates an empty steering mailbox; messages submitted under the new version have no equivalent mailbox entry. Restore the old runtime and frontend together.

## Limitations

Immediate in-thread submission accepts plain text in active ReAct and Deep turns. Graph execution, commands, attachments and human-input answers retain their existing send paths. An interrupted or unavailable model boundary leaves the new message pending until a later eligible turn.
