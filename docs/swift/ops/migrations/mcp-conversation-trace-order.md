---
schema: 1
title: "Place MCP tools in their conversation trace branches"
impact: none
configuration: none
configuration_reason: "Fred links captured MCP invocations to existing spans using the current conversation trace settings."
no_action_reason: "The runtime writes the existing evidence reference on new spans during normal operation. No data migration is needed."
after: [long-conversation-trace-capture]
---

## Applicability

Fred deployments using conversation trace capture.

## Prerequisites

The conversation must be eligible for capture under the existing trace policy.

## Configuration

No configuration changes are required.

## Upgrade

Follow the trace storage rollout procedure in this release before validating tool placement.

## Validation

Capture a new Deep turn that runs MCP tools in parallel tasks. Open the turn in
Fred Admin and verify that each tool appears in the task that ran it, between
the model calls that requested it and received its result.

## Rollback

Use the normal rollback procedure.

## Limitations

Previously stored traces retain their original span metadata. Validate the fix
with a new capture.
