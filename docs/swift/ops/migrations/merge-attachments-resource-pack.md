---
schema: 1
title: "Combine team resources and conversation attachments in the agent form"
impact: none
configuration: none
configuration_reason: "The change is confined to the frontend agent form; production configuration keys and defaults are unchanged."
no_action_reason: "Existing agent selections and backend APIs are unchanged on deployment; the new Simple pack applies only when a member enables it."
---
## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. The Simple agent form offers one resource pack that enables both team corpus access and conversation attachments. Existing agents retain their selected capabilities and document-access settings. A partial legacy selection may leave the new pack switch off while its selected capabilities remain active in Advanced. Enabling the pack and saving selects the full available bundle.

## Validation

Create an agent, enable the resource pack, and confirm team corpus access and conversation attachments are available. For an existing attachments-only agent, confirm Advanced still permits attachments without corpus search and an unrelated save does not broaden its access.

## Rollback

Use the normal rollback procedure. There is no data migration. A full bundle deliberately saved by a member remains in the agent record and is not reverted automatically.

## Limitations

Advanced can retain a narrower document-access selection than the Simple pack offers. The Simple pack switch reads off for such partial selections.
