---
schema: 1
title: "Fix HTML artifact PNG/PDF export in Chrome and Edge"
impact: none
configuration: none
configuration_reason: "Only the frontend export code of HTML artifacts changes; no configuration keys or defaults change."
no_action_reason: "The fix is client-side rasterization only; existing data, APIs and artifacts are unchanged and it takes effect with normal deployment."
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

In Chrome or Edge, open an HTML artifact, choose PNG then PDF in its download menu, and check that both files download instead of showing "Could not export the PNG.".

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
