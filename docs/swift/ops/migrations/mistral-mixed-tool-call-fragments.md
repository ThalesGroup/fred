---
schema: 1
title: "Recover Mistral tool calls from mixed content fragments"
impact: none
configuration: none
configuration_reason: "Only the fred-runtime parser and stream bridge change; no configuration keys, defaults, or chart values change."
no_action_reason: "Existing data and APIs are unchanged; the fix takes effect when the updated runtime is deployed normally."
---

## Applicability

Fred deployments using Mistral Medium with reasoning enabled and ReAct or Deep agents.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Ask an agent using Mistral Medium with reasoning to answer a question that requires a registered tool. Confirm the tool executes and its encoded call syntax does not appear in the answer.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

Recovery still requires the exact empty typed reference sentinel and valid arguments for a registered tool. It does not interpret arbitrary text as a tool call.
