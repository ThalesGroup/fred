---
schema: 1
title: "Select resource rows and open folders or files with a double-click"
impact: none
configuration: none
configuration_reason: "Only frontend interaction and translation changes; no configuration keys or defaults change."
no_action_reason: "Existing data and APIs are unchanged; the interactions become available after normal deployment."
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

Click a folder or file name and verify that only its row is highlighted. Ctrl/Cmd-click another row to select both. Drag over either name to select and copy its text. Double-click a folder row to open it, or a file row to open its preview.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
