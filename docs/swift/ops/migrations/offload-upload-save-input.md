---
schema: 1
title: "Keep Knowledge Flow responsive while an upload is written to the content store"
impact: none
configuration: none
configuration_reason: "Only moves the existing content-store write of an upload to a worker thread; no configuration keys or defaults change."
no_action_reason: "Upload endpoints, stored data and write order are unchanged; the fix takes effect with a normal deployment."
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

Upload a large document and, while it is being stored, browse team resources
from another tab: the listing keeps answering instead of waiting for the upload.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

Other synchronous content-store calls (preview output, bulk folder deletion)
still run on the event loop and are tracked separately.
