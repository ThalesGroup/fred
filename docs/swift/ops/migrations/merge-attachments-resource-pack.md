---
schema: 1
title: "Combine resource capabilities and enable tabular conversation attachments"
impact: none
configuration: none
configuration_reason: "The agent form and attachment ingestion change without new production configuration keys or defaults."
no_action_reason: "Existing agent selections remain unchanged; new Excel attachments use the existing corpus Excel processors automatically."
---
## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. The Simple agent form offers one resource pack that enables both team corpus access and conversation attachments. Existing agents retain their selected capabilities and document-access settings. A switch below library scoping narrows document search to conversation attachments and withdraws comparison while retaining tabular tools. A complete former attachments-pack selection reads on with that scope selected; an incomplete legacy selection may leave the pack off while its selected capabilities remain active in Advanced. Enabling an off pack and saving selects the full available bundle.

## Validation

Create an agent, enable the resource pack, and confirm team corpus access and conversation attachments are available. Select the attachments-only switch and confirm corpus document search and comparison are unavailable while tabular tools remain enabled. Attach a multi-sheet Excel workbook, describe its tables, and query rows beyond the preview shown in the attachment card. For an existing attachments-only agent, confirm the Simple pack reflects the stored scope and an unrelated save does not broaden its access.

## Rollback

Use the normal rollback procedure. There is no data migration. A full bundle deliberately saved by a member remains in the agent record. New Excel attachments created after upgrade retain multi-table artifacts; an older backend cannot query them until the newer version is restored.

## Limitations

Previously uploaded Excel attachments remain text-backed and may contain only a truncated preview. Advanced can retain a narrower document-access selection than either complete Simple profile. The Simple pack switch reads off for such partial selections.
