---
schema: 1
title: "Recover malformed tool names in Mistral conversations"
impact: none
configuration: none
configuration_reason: "Tool-name resolution and Mistral request formatting change without new settings or defaults."
no_action_reason: "Conversation history is adapted when building the model request, so existing checkpoints need no rewrite."
---
## Applicability

Existing Fred deployments using ReAct or Deep tool calls, including conversations
with previously rejected tools on Mistral Chat Completions.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. Existing sessions pick up the repair on their next model call.

## Validation

Continue a Mistral conversation with a rejected dotted tool name in its history.
The next model request should succeed and include an error for the skipped tool.

## Rollback

Use the normal rollback procedure. This change introduces no data migration.

## Limitations

MCP tool definitions still use their published names. A strict endpoint can
reject a dotted MCP definition before the model emits any tool call.
