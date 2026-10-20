---
schema: 1
title: "Give every agent the current date at model invocation"
impact: none
configuration: none
configuration_reason: "The runtime supplies the date; no deployment setting changes."
no_action_reason: "The runtime adds the date at each model call, so saved prompts and stored data need no migration."
---
## Applicability

Deployments running ReAct, Deep, or Graph agents.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy fred-runtime normally. Existing and new agents receive the current UTC
date at model invocation without prompt edits.

## Validation

Ask an existing ReAct, Deep, and Graph agent for today's date. The model input
should contain the current UTC date and instruct a date-only answer.

## Rollback

Use the normal rollback procedure. No stored data migration is involved.

## Limitations

The date uses the UTC calendar, which may differ from a user's local date around
midnight. Graph handlers must use the supported `NodeContext` model methods to
receive the date instruction.
