---
schema: 1
title: "Weaver: persist in-progress chat updates in conversation history"
impact: minor
configuration: none
configuration_reason: "The existing runtime database and conversation access controls carry pending messages; no new service, credential or chart value is introduced."
---
## Applicability

Fresh Weaver installations using managed Python ReAct, Deep or Graph agents.
This integrates Swift #3493. Embedded Ralph does not acquire steering support.

## Prerequisites

Initialize Control Plane before the runtime, using the existing initialization
commands and schema grants. Deploy matching frontend, SDK and runtime sources.

## Configuration

No new configuration is required. The runtime migration `d0e1f2a3b4c5`, following
`c9d0e1f2a3b4`, adds message identity and delivery state to `session_history` and
removes `runtime_turn_steering`. Existing migrations remain unchanged. Conversation
foreign keys and physical erasure also cover pending messages.

## Upgrade

Only fresh installations are supported. Initialize the complete migration chain
before starting the Python pod. Reusing an incompatible local database requires
its separately authorized recreation; this change does not migrate Swift data or
provide a rolling upgrade. No database is reset by the integration itself.

## Validation

Send a text update while an agent works. Its message appears immediately with a
clock; ReAct/Deep deliver it at a model boundary after checkpoint persistence.
Reload and verify message order and delivery state. A message not delivered before
the turn ends opens the next ordinary turn, including after reopening the chat;
a pending human-input request keeps that continuation waiting. Graph uses this
next-turn fallback rather than modifying a running graph.

Check rejection from another user, space or agent, retries without duplicate
messages, and conversation deletion. Keep the existing attachment and HITL checks.
These deployed acceptance checks remain the developer's responsibility.

## Rollback

Reinstall matching previous sources on a fresh database. PostgreSQL downgrade of
this migration is refused rather than restoring a mailbox without conversation
ownership. Existing Weaver upgrades and data recovery remain unsupported.

## Limitations

An in-flight tool is not interrupted. Delivery acknowledges model input, not
correct model interpretation or an immediate answer. Reopening a conversation may
start an additional model turn for a pending message. Pending updates are text-only
and limited to 32 per conversation/user. Managed ReAct/Deep checkpoint persistence
is synchronous at graph steps. No deployed performance or PostgreSQL validation
is claimed by this merge's offline checks.
