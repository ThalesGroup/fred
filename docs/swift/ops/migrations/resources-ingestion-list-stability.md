---
schema: 1
title: "Keep Resources folder listings stable during ingestion"
impact: none
configuration: none
configuration_reason: "The change only adjusts frontend request ordering and loading display."
no_action_reason: "Normal deployment supplies the updated frontend; no data, API, or configuration changes are required."
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

Open a populated Resources folder during document ingestion. Its rows should remain visible through background refreshes.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

This change does not address the backend authorization result limit tracked in #2845.
