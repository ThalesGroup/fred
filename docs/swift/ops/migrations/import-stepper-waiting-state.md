---
schema: 1
title: "Show queued imports as waiting in the import panel"
impact: none
configuration: none
configuration_reason: "Only the frontend import panel changes; no configuration keys or defaults change."
no_action_reason: "Display-only frontend change; it applies with the normal frontend deployment."
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

Import more files at once than the ingestion workers run in parallel: the files not yet picked up read "Waiting…" with a still grey marker, then switch to the usual running phases.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
