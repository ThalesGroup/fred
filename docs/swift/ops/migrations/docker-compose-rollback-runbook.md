---
schema: 1
title: "Document Docker Compose rollback and Kubernetes migration caveat"
impact: none
configuration: none
configuration_reason: "Only operator documentation changes; no deployment configuration or defaults change."
no_action_reason: "Existing deployments and data are unchanged; the new runbook applies when planning a future upgrade or rollback."
---
## Applicability

Operators planning a Fred deployment or rollback with site-owned Docker Compose
files, and operators using the Fred Helm chart.

## Prerequisites

No action is needed for the currently running deployment.

## Configuration

No configuration changes are required.

## Upgrade

Deploy normally. Before a future upgrade, review the new rollback runbook and
the release-specific migration guide.

## Validation

The runbook identifies the separate Alembic version tables, migration commands,
backup boundary and rollback paths for Compose and the Helm rollback caveat.

## Rollback

Use the normal rollback procedure; this documentation change has no data migration.

## Limitations

The runbook is a template for site-owned Compose deployments, not a production
Compose manifest or an automated database rollback.
