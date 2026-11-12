---
schema: 1
title: "Prevent invented HTML artifact links in chat responses"
impact: none
configuration: none
configuration_reason: "Only the HTML artifact tool's success text changes; no configuration keys or defaults change."
no_action_reason: "The existing preview and artifact payload are unchanged; normal deployment applies the new model guidance."
---

## Applicability

Weaver agent pods with the HTML artifact capability enabled.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy the updated agent pod normally; no data migration or additional operator
action is required for this change.

## Validation

Ask an agent to create an HTML page and provide a link. Check that the tool's
success result forbids inventing a URL and directs the model to the right-side
preview, the artifact card to open or reopen it, and the panel's close button.

## Rollback

Revert the tool guidance with the previous compatible agent pod image; this
change introduces no data migration.

## Limitations

This is model guidance, not a guarantee about generated answers. It does not
create a hosted or shareable artifact URL or change the existing UI controls.
The card can open the preview even when the UI does not automatically open it.
