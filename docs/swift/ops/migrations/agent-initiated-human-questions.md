---
schema: 1
title: "Enable agent-initiated human questions"
impact: minor
configuration: none
configuration_reason: "The control is delivered by execution preparation and uses no operator configuration key."
---
## Applicability

Fred deployments upgrading the control plane, agent runtime, SDK and frontend.

## Prerequisites

Use a release containing the SDK, runtime, control plane and frontend changes.

## Configuration

No configuration or data migration is required. Existing HITL history remains readable.

## Upgrade

Deploy the SDK and agent runtime first, then the control plane and frontend. The
control plane then offers the question control, enabled by default. Older clients
that omit `ask_user` continue without the tool.

## Validation

In managed chat, verify that the tune menu offers agent questions, the agent can
ask one question, answer and skip both continue the turn, and a skipped answer
remains visible after reload.

## Rollback

Withdraw the control plane and frontend exposure first. Let already-pending
agent questions finish on the new runtime before rolling back the runtime and
SDK; an older runtime cannot resume those checkpointed tool calls. No database
migration must be reversed.

## Limitations

The platform tool is available on interactive ReAct and Deep parent turns. Graph
agents and Deep child agents do not gain a model-facing question tool.
