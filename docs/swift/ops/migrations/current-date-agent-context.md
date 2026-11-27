---
schema: 1
title: "Supply the current UTC date to agent model calls"
impact: minor
configuration: none
configuration_reason: "Agent pods supply the UTC date at model-call time; no configuration key or default changes."
---

## Applicability

Existing deployments upgrading agent pods with the new fred-runtime.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy updated agent pods normally. Existing agent instances receive the date
without a prompt or data migration. The `{today}` prompt token is retired;
stored prompts containing it remain unchanged and send that text literally to
the model. Authors relying on its substitution can revise those prompts, but
no edit is required for an agent to know the current date. External pods using
older images keep their previous behavior until updated.

## Validation

Ask an existing ReAct agent without `{today}` what today's date is. It should
answer with the current UTC calendar date, without a time. Repeat with an
agent whose stored prompt still contains `{today}`: the agent should know the
same date, while the stored prompt remains unchanged. Check a Graph agent
using `NodeContext.invoke_model` or `invoke_structured_model` if deployed.

## Rollback

Use the normal rollback procedure; no stored data was migrated. Older pods
resume their prior `{today}` substitution behavior.

## Limitations

The runtime supplies the UTC date, not the user's local date or current time.
Graph nodes calling `context.model` directly are outside this guarantee.
