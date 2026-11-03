---
schema: 1
title: "Raise the per-turn tool call limit to 100"
impact: none
configuration: none
configuration_reason: "The existing agent tool-selection policy changes its default cap; deployment settings are unchanged."
no_action_reason: "The updated policy takes effect with a normal agent deployment."
---
## Applicability

Managed Weaver agents using the shared ReAct tool-selection policy.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy the updated agent image normally.

## Validation

A turn may now execute more than 12 tool calls, up to the new limit of 100.

## Rollback

Use the previous agent image. No data migration is involved.

## Limitations

The limit still stops additional tool calls once reached; the agent then answers
from the results already available.
