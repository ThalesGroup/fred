---
schema: 1
title: "Give generic assistants the current date in their default prompts"
impact: none
configuration: none
configuration_reason: "Only the bundled generic assistant prompt text changes; no deployment setting changes."
no_action_reason: "The existing runtime expands the date token, so normal fred-agents deployment is enough and no stored data needs migration."
---
## Applicability

Deployments offering the generic ReAct or Deep assistant templates.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy fred-agents normally. New generic assistant instances receive the updated
English or French default prompt.

## Validation

Create a generic ReAct or Deep assistant and ask for today's date. Its default
prompt should contain the current UTC date and instruct a date-only answer.

## Rollback

Use the normal rollback procedure. No stored data migration is involved.

## Limitations

Existing instances with a saved prompt, including a copy of the previous
default, keep that prompt until edited. The date token uses the UTC calendar
date, which may differ from a user's local date around midnight.
