---
schema: 1
title: "Attribute generated PowerPoint files to the acting user"
impact: none
configuration: none
configuration_reason: "Only generated Office file metadata changes; no configuration keys, defaults, or chart values change."
no_action_reason: "New downloads use the existing authenticated identity without changing stored templates, APIs, permissions, or existing files. Normal deployment is sufficient."
---
## Applicability

Existing Fred deployments using PPT Filler or PPT Builder.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Generate a deck with PPT Filler and PPT Builder from a template with a different
creator. Check that each downloaded PPTX has the acting user's name in both
Author and Last Modified By, while the source template retains its metadata.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

Previously downloaded files retain their metadata. Generate them again to get
the corrected attribution. Names are limited to 255 characters in the files.
