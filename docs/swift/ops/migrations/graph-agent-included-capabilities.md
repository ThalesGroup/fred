---
schema: 1
title: "Show and configure the capabilities included with graph agents; enforce library binding on knowledge.search"
impact: none
configuration: none
configuration_reason: "Only the agent template contract, the agent form and the knowledge.search scope change; no configuration key or default changes."
no_action_reason: "No data is migrated: existing agent instances keep running their included capabilities as before, and gain a stored configuration only when someone edits and saves them."
---
## Applicability

Existing Fred deployments upgrading to this release, in particular those using
graph agents (for example mindmap or comparison) that include `document_access`.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required. The
runtime pods and the control plane may be upgraded in either order.

## Validation

Create a mindmap agent bound to one library in the Capabilities tab, under
"Included with this agent". In a conversation, the library selector is pinned
to that library and the sources come only from it.

## Rollback

Use the normal rollback procedure; this change introduces no data migration. A
configuration saved for an included capability stays stored and is ignored by
an older form.

## User-visible message

A turn refused because the team has not enabled the agent's model used to read
"The agent could not initialize its execution. Contact support with reference
…". It now names the model and tells the user to ask a platform administrator
to enable it for the team; the support reference stays.

## Limitations

An instance created before this release keeps an empty stored selection, so its
chat shows no capability controls until it is edited and saved once. The
builtin `knowledge.search` now stays within an instance's bound libraries for
every client, including API runs without the chat UI, and the `document_access`
search and tree find nothing for a selection outside the libraries the agent is
bound to, where they used to search unfiltered.
