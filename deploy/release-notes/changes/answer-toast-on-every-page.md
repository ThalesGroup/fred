---
schema: 1
title: "Announce a finished chat answer on every page, including admin and settings"
impact: none
configuration: none
configuration_reason: "Only where the frontend listens for finished answers changes; no configuration keys, defaults or chart values are involved."
no_action_reason: "The runtime and its APIs are unchanged; the toast is raised by the browser, so normal deployment is enough."
---
## Applicability

Weaver browser sessions upgrading to this release. Port source:
Swift `0773ff95d2dcde7c810e88c67cdbfed1e0d078a9` (#3428).

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Ask an agent a question with a long answer, open an admin page while it streams,
and wait: an "Answer ready" toast appears with an Open action to the conversation.
Verify that the conversation sidebar does not produce a second toast for the
same completion. Check navigation to the originating conversation and ensure
that a previous signed-in identity does not notify the current one. These are
deployment reception scenarios, not claims of browser validation during the merge.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

The toast is raised only in the browser tab that asked the question, and not
after the page was reloaded. It is not an operating-system notification or a
durable completion feed; conversation access continues to use Weaver's current
authorization checks.
