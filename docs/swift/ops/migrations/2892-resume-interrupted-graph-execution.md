---
schema: 1
title: "Offer to continue a Graph run interrupted by a lost process"
impact: none
configuration: none
configuration_reason: "Runtime and frontend behaviour only; no configuration key, default or chart value changes."
no_action_reason: "No schema or data migration: detection reads existing checkpoints and the single-use claim reuses the existing HITL claim table."
---
## Applicability

Existing Fred deployments upgrading to this release, for Graph agents only.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure. Deploy the
runtime and the frontend of the same release.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. Graph checkpoints are now written synchronously per step.
A conversation whose Graph thread was already left with pending steps before the
upgrade is offered **Continue** or **Restart** on its next message. If the
interrupted step fails again on Continue, the thread is cleared and the next
message behaves as before.

## Validation

Stop the runtime pod while a Graph agent is between two steps, restart it, and
send a message in that conversation: the chat shows the interruption card, and
**Continue** finishes the run without repeating completed steps.

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
