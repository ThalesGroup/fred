---
schema: 1
title: "Install LibreOffice Writer for Word template PDF previews"
impact: none
configuration: none
configuration_reason: "Only the fred-agents image packages change; no runtime or chart settings change."
no_action_reason: "A normal image rollout installs Writer; no data migration or special deployment step is needed."
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

Generate a document with a Word template and open its PDF preview. Check that a PPT Builder preview still opens.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
