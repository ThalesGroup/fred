---
schema: 1
title: "Name new conversations with a generated title"
impact: none
configuration: none
configuration_reason: "The title uses the pod's existing default chat profile; no configuration keys or defaults change."
no_action_reason: "The runtime contract gains one optional request field (`runtime_context.auto_title`) and one stream event (`session_title`). The existing session PATCH stores the title. There is no data migration and no permission change, so a normal deployment is enough."
---
## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. No additional operator or user action is required.

## Validation

Start a new conversation and send a long first message. While the answer is streaming, the sidebar and the chat header switch to a short generated title (3 to 8 words) instead of the beginning of the message. Later messages do not change the title. Renaming the conversation by hand still works and is kept.

## Rollback

Use the normal rollback procedure. This change introduces no data migration, and titles that were already generated stay as they are.

## Limitations

Each new conversation makes one extra small call on the pod default chat model, outside the agent's own model selection. Its input is bounded to 600 characters and the title is short. If that call fails, or is still running 2 s after the answer ends, the conversation keeps the beginning of the first message as its title. Conversations created before the upgrade keep their current titles.
