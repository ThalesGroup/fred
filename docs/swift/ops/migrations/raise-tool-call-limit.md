---
schema: 1
title: "Raise the per-turn tool call limit to 100"
impact: none
configuration: none
configuration_reason: "The limit is a code constant in fred-agents; no configuration key or chart value changes."
no_action_reason: "Existing data and APIs are unchanged; the higher limit takes effect with normal deployment."
---
## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Run a turn that needs more than 12 tool calls and check that the agent keeps receiving tool results past the twelfth call.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

A runaway turn can now make up to 100 tool calls before it is stopped, so its token and latency cost is higher than before.
