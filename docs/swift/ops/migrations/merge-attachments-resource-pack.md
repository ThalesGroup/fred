---
schema: 1
title: "Combine team resources and conversation attachments in the agent form"
impact: none
configuration: none
configuration_reason: "The change is confined to the frontend agent form; production configuration keys and defaults are unchanged."
no_action_reason: "Existing agents and backend APIs are unchanged on deployment; members opt into the combined pack when they re-enable it in the agent form."
---
## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. The Simple agent form shows one resource pack that enables team corpus access and conversation attachments. Existing agents keep their stored settings on deployment and unrelated edits. A member can turn the pack off and on, then save, to adopt the combined default.

## Validation

Create an agent, enable the resource pack, and confirm that team resources and conversation attachments are available. For an existing agent, check that an unrelated edit leaves its attachment setting intact.

## Rollback

Use the normal rollback procedure. There is no data migration. Settings deliberately saved after re-enabling the combined pack remain in the agent record and are not reverted automatically.

## Limitations

The Advanced view can still disable attachments for an agent whose resource pack is on. That explicit setting persists across later unrelated edits.
