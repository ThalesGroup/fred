---
schema: 1
title: "Archive the weaver UI port and turn attachments OpenSpec changes"
impact: none
configuration: none
configuration_reason: "Only OpenSpec documents move to the archive; no configuration keys or defaults change."
no_action_reason: "Documentation only; no code, data or API changes, so normal deployment is enough."
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

Run `openspec validate frontend-shell-layout --type spec --strict` and check that it passes.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
