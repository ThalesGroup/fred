---
schema: 1
title: "Reject PowerPoint templates without fields"
impact: none
configuration: none
configuration_reason: "Only PPT Filler upload validation and translated form guidance change; no configuration keys, chart values, or permissions change."
no_action_reason: "Normal deployment enables validation for new uploads; existing saved templates and data require no migration."
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

Select a PowerPoint without template fields in both agent forms. Verify saving is
blocked with translated guidance and a link to `/ppt-filler-help`. Verify templates
using `{title}` or `{{title}}`, including fixed slides, still save normally.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
