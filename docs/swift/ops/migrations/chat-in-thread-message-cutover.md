---
schema: 1
after: [chat-active-turn-steering]
covers: [28d9ee7c7a232247dfa01838a2624ce21028c53c]
title: "Replace active-turn steering with in-thread messages"
impact: major
configuration: none
configuration_reason: "The new runtime uses the existing shared session_history table and adds no configuration keys, but the schema migration removes the old steering mailbox."
---
## Applicability

Fred deployments upgrading from the browser queue and runtime steering mailbox
to in-thread messages during active ReAct and Deep turns.

## Prerequisites

Stop or drain old runtime replicas before applying the new fred-runtime Alembic
migration. Old replicas must not serve requests after the steering table is
removed. Coordinate the matching frontend rollout with the runtime rollout.

## Configuration

No configuration changes are required. The new message state lives in the
existing shared `session_history` table.

## Upgrade

The migration adds message identity and delivery state to `session_history` and
drops `runtime_turn_steering`. Apply it after draining old runtime replicas,
then start the new replicas and deploy the matching frontend. Messages still
pending in the old mailbox or browser queue are discarded. Ask users to resend
an old pending message if it did not appear in their conversation.

## Validation

With two runtime replicas, start a ReAct or Deep turn on one pod and submit
another text message through the other. Confirm its pending indicator, final
rank after the next model boundary, and order after a page reload. Repeat across
a human-input pause and a restart. The migration downgrade test also verifies
that the old steering table returns at its previous revision and disappears at
the current head without changing capability migration revisions.

## Rollback

Stop the new runtime replicas before downgrading the migration. The downgrade
recreates an empty steering mailbox; messages submitted under the new version
have no equivalent mailbox entry. Restore the old runtime and frontend together.

## Limitations

Immediate in-thread submission accepts plain text in active ReAct and Deep
turns. Graph execution, commands, attachments and human-input answers retain
their existing send paths. An unavailable model boundary leaves the new message
pending until a later eligible turn.
