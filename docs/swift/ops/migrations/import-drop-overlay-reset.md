---
schema: 1
title: "Clear the Resources drop overlay after dropping into a folder"
impact: none
configuration: none
configuration_reason: "Only the Resources page drag-and-drop state changes; no configuration keys or defaults change."
no_action_reason: "The frontend clears its overlay after a file is dropped on a folder row; data and APIs are unchanged."
covers: [444c61b93f607a7857cc6bd7427ca5434e34594b]
---
## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Drag a file over Team Resources and drop it on a subfolder row. The import dialog targets that subfolder and the full-page drop overlay disappears.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
