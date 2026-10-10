---
schema: 1
title: "Make agents use the question tool and accept open questions"
impact: none
configuration: none
configuration_reason: "Only the ask_user tool description and argument handling in fred-runtime change; no configuration key, chart value or permission changes."
no_action_reason: "The human-input contract and stored history are unchanged; agents receive the new tool description on their next turn after a normal deployment."
---
## Applicability

All Fred deployments where conversations enable agent questions.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

With agent questions enabled, ask an agent to ask you a multiple-choice
question: the card shows a single editable "Other" row, never a second plain
"Other" choice. Ask it for information it cannot guess, such as a recipient's
email address: the conversation pauses on a free-text question instead of
failing the turn.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

The tool description asks agents to use the tool instead of asking in their
reply, but cannot force them to; a model may still ask in plain text.
