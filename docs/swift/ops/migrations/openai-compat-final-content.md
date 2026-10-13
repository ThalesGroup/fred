---
schema: 1
title: "Deliver non-streamed final answers on the OpenAI-compatible endpoint"
impact: none
configuration: none
configuration_reason: "Only the /v1/chat/completions stream mapping changes; no configuration keys or defaults change."
no_action_reason: "The endpoint keeps its request and chunk shapes; clients now also receive answer text that was previously dropped, with normal deployment."
---
## Applicability

Existing Fred deployments upgrading to this release, relevant only to agent pods
with `app.openai_compat: true`.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

On a pod with `app.openai_compat: true`, call `/v1/chat/completions` with an agent
whose only tool call fails, and check that the last chunk's `delta.content` carries
the error text instead of being empty.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
