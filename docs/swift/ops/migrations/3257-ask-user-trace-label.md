---
schema: 1
title: "Localize the agent question label in the chat trace"
impact: none
configuration: none
configuration_reason: "Only the frontend label for the ask_user trace entry changes; no configuration keys or defaults change."
no_action_reason: "Existing conversations render with the localized label after a normal deployment; runtime behavior, stored data and APIs are unchanged."
---

## Applicability

Existing Fred deployments using managed chat.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Open a conversation where an agent asked the user a question and expand its tool
trace. The row and detail drawer show "Demande d'information à l'utilisateur" in
French or "Requesting information from the user" in English.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
