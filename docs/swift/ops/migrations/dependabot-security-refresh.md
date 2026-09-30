---
schema: 1
title: "Refresh vulnerable Python and npm dependencies"
impact: none
configuration: none
configuration_reason: "Dependency and lockfile updates do not add or change configuration keys or defaults."
no_action_reason: "Existing data, APIs, and deployment order are unchanged; rebuilt images and frontend assets take effect through normal deployment."
---
## Applicability

Existing Fred deployments upgrading to a release that includes the dependency refresh.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy the updated backend images and frontend assets normally. No data migration or re-ingestion is required.

## Validation

Confirm the services start, a normal authenticated request succeeds, a representative document is ingested, and the frontend loads.

## Rollback

Use the normal image and asset rollback procedure. Rolling back restores vulnerable dependency versions; redeploy a corrected release as soon as possible.

## Limitations

This note covers deployed artifacts built from the corrected locks. Independently built or older images retain their own dependency versions.
