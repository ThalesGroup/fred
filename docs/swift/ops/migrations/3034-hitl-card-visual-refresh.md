---
schema: 1
title: "Refresh the agent question and tool approval cards"
impact: none
configuration: none
configuration_reason: "Only frontend styling, layout and labels of the human-input cards change; no configuration key, chart value or permission changes."
no_action_reason: "The runtime contract, answer semantics and stored history are unchanged; existing conversations render with the new cards after a normal deployment."
---
## Applicability

All Fred deployments using managed chat.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Ask an agent a question with choices. The card shows numbered full-width
choices, an "Other" input field, a "Skip" action with an ESC key hint and no
close cross; pressing a number key picks that choice while the composer is held.
Approve a gated tool and check that the reply bubble names the tool and the
decision.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

"Approve for this conversation" is remembered in the browser and stored as a
plain approval, so after a reload its reply reads "Accepted".
