---
schema: 1
title: "Clarify tool actions in the chat trace"
impact: none
configuration: none
configuration_reason: "Only frontend action labels and their translations change; no configuration keys or defaults change."
no_action_reason: "Existing conversations, tool execution and APIs are unchanged; the new labels appear after a normal deployment."
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

Open a chat trace that used a tabular query or an OpenSearch tool and check that the action appears in the selected UI language.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

Namespaced external MCP tools without a dedicated translation continue to use the generic label fallback. Older traces do not record tool provenance, so an unprefixed external tool sharing a known Fred tool name receives the same label.
